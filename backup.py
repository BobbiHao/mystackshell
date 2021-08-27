#!/usr/bin/python3
import logging
logging.basicConfig(level=logging.DEBUG)
import time
import os
import string
import socket
import contextlib
import ftplib
import pymysql

global INI_FILE
INI_FILE = os.getcwd() + '/backup.ini'
global REDIS_TMP
REDIS_TMP = '/tmp/redis-save'
dic = {}

DATABASE_NAME = 'backup'

daytime = time.strftime("%Y-%m-%d", time.localtime())
datetime = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())

print("daytime is ", daytime)
print("datetime is ", datetime)

class MyFTP(ftplib.FTP):
    def mkpath(self, dirpath):
        head, tail = os.path.split(dirpath)
        if not tail:
            head, tail = os.path.split(head)
        if head and tail and not os.path.exists(head):
            self.mkpath(head)
        try:
            self.mkd(dirpath)
        except:
            pass
    def ftp_check_and_mkpath(self, dirpath) -> int:
        try:
            self.cwd(dirpath)
        except Exception as e:
            logging.debug(e)
            try:
                self.mkpath(dirpath)
            except Exception as e:
                logging.debug(e)
                return 1
            else:
                return 0
        else:
            return 0


def get_installcmd():
    os_VENDOR = os.popen("lsb_release -i -s").read().strip('\n')
    print("os_VENDOR is ", os_VENDOR)
    if os_VENDOR.find("Debian") or os_VENDOR.find("Ubuntu") or os_VENDOR.find("LinuxMint"):
        return "apt"
    else:
        return "dnf"

def get_package(cmd, package):
    installcmd = get_installcmd()
    isExist = os.system("which %s" %cmd)
    if isExist != 0:
        i = os.system("%s install %s" %(installcmd, package))
        if i != 0:
            print("%s is install failed" %package)
            exit(1)

def get_value(section, key):
    res = os.popen("crudini --get %s %s %s 2>/dev/null" %(INI_FILE, section, key)).read().strip('\n')
    return res

def get_section():
    return get_value('', '').split('\n')

def check_and_mkpath(dir):
    if os.path.exists(dir) and os.path.isdir(dir) == False:
        logging.error("%s is exist but not a dir" %dir)
        exit(1)
    if os.path.exists(dir) == False:
        logging.info("mkdir %s" %dir)
        os.system("mkdir %s -p" %dir)

def add_dic_from_ini():
    backup_type = get_value('backup', 'backup_type')
    logging.info("INIT DIC FROM INI")

    sections = get_section()
    for key in sections:
        logging.debug("now in add_dic_fomr_ini, key is %s" %key)
        src_path = unit = data_type = backup_dst = backup_remotedst = backup_period = backup_volume = save_time = ''
        if key == 'conf' or key == 'scp' or key == 'ftp' or key == 'backup' or key == 'restore':
            continue

        if key.startswith('/'):
            src_path = key
        else:
            if key == 'redis':
                src_path = REDIS_TMP
            else:
                logging.error("%s is not begin with / , and it is no redis, exit!")
                exit(1)

        unit = get_value(key, 'unit')
        data_type = get_value(key, 'data_type')

        if backup_type == 'local':
            backup_dst = get_value(key, 'backup_dstdir')
        else:
            backup_dst = '-'

        if backup_type == 'scp' or backup_type == 'ftp':
            backup_remotedst = get_value(key, 'remote_dstdir')
        else:
            backup_remotedst = '-'

        backup_period = get_value(key, 'backup_period')
        backup_volume = get_value(key, 'backup_volume')
        save_time = get_value(key, 'save_time')

        if backup_dst == '' and backup_type == 'local':
            logging.warning("get_value %s backup_dstdir is null, skip!" %key)
            continue
        if backup_remotedst == '' and (backup_type == 'scp' or backup_type == 'ftp'):
            logging.warning("get_value %s remote_dstdir is null, skip!" %key)
            continue

        logging.debug("unit is %s" % unit)
        logging.debug("data_type is %s" % data_type)
        logging.debug("backup_dst is %s" % backup_dst)

        dic[src_path] = {
            'unit': unit,
            'data_type': data_type,
            'backup_dst': backup_dst,
            'backup_remotedst': backup_remotedst,
            'backup_period': backup_period,
            'backup_volume': backup_volume,
            'save_time': save_time
        }
    logging.info("INIT DIC FROM INI END")


def save_redis() -> int:
    redis_values = get_value('redis', '').split('\n')
    logging.debug("redis_values is %s" % redis_values)
    if not redis_values:
        logging.warning("ini has no redis, skip to save it")
        return 1
    check_and_mkpath(REDIS_TMP)
    os.system("rm -rf %s/*" % REDIS_TMP)

    if os.system("redis-cli CONFIG GET dir > /dev/null") != 0:
        logging.warning("exit from save_redis")
        return 1

    if os.system("redis-cli CONFIG GET dir | grep \"NOAUTH Authentication required\"") == 0:
        password = get_value('redis', 'server-password')
        if password == '':
            exit(1)
        PASS = "-a %s" %password
    else:
        PASS = ''
    logging.debug("PASS is %s" % PASS)

    if os.system("redis-cli %s CONFIG SET dir %s > /dev/null" % (PASS, REDIS_TMP)) != 0:
        return 1
    if os.system("redis-cli SAVE > /dev/null") != 0:
        logging.warning("redis data save failed!!!")
        return 1
    logging.info("redis data save succeed...")
    return 0


def create_mysql():
    create_database_sql = "CREATE DATABASE IF NOT EXISTS backup"

    create_table_sql = "CREATE TABLE IF NOT EXISTS backup.etc_backup (" \
                        "uuid VARCHAR(45) NOT NULL," \
                        "servername VARCHAR(45) NOT NULL," \
                        "filename VARCHAR(1024) NOT NULL," \
                        "srcpath VARCHAR(1024) NOT NULL," \
                        "dstdir VARCHAR(1024) NOT NULL," \
                        "remotedir VARCHAR(1024) NOT NULL," \
                        "createtime DATETIME NOT NULL," \
                        "backup_per VARCHAR(45) NOT NULL," \
                        "backup_sto VARCHAR(45) NOT NULL," \
                        "save_time VARCHAR(45) NOT NULL," \
                        "PRIMARY KEY(uuid)," \
                        "UNIQUE INDEX uuid_etc_bakup_UNIQUE(uuid ASC) VISIBLE);"

    password = get_value('conf', 'mysql_password')
    logging.info("mysql -u root -e '%s' -p'%s' >/dev/null" % (create_table_sql, password))
    if os.system("mysql -u root -e '%s' -p'%s' >/dev/null" % (create_table_sql, password)) != 0:
        exit(1)

def splice_tarfilename(servername, srcpath, data_type) -> string:
    _datetime = datetime.replace(' ', '_')
    srcpath_changed = srcpath.replace('/', '_')

    filename = "%s_%s_%s" % (socket.gethostname(), _datetime, servername)
    while filename[-1] == '_':
        filename=filename[:-1]
    filename += srcpath_changed
    while filename[-1] == '_':
        filename=filename[:-1]
    filename = "%s_%s.tar.gz" % (filename, data_type)
    return filename


@contextlib.contextmanager
def pushd(new_dir):
    previous_dir = os.getcwd()
    os.chdir(new_dir)
    try:
        yield
    finally:
        os.chdir(previous_dir)

def get_a_insert_record(key) -> dict:
    oneline = dict()
    oneline['srcpath'] = key
    oneline['unit'] = dic[key]['unit']
    oneline['data_type'] = dic[key]['data_type']
    oneline['backup_dst'] = dic[key]['backup_dst']
    oneline['backup_remotedst'] = dic[key]['backup_remotedst']
    oneline['backup_period'] = dic[key]['backup_period']
    oneline['backup_volume'] = dic[key]['backup_volume']
    oneline['save_time'] = dic[key]['save_time']
    oneline['uuid'] = os.popen("uuidgen").read().strip('\n')
    oneline['filename'] = splice_tarfilename(oneline['unit'], oneline['srcpath'], oneline['data_type'])
    logging.debug("srcpath: %s, unit: %s, data_type: %s, backup_dst: %s, backup_remotedst: %s, backup_period: %s, "
                  "backup_volume: %s, save_time: %s" % (oneline['srcpath'], oneline['unit'], oneline['data_type'], oneline['backup_dst'],
                    oneline['backup_remotedst'], oneline['backup_period'], oneline['backup_volume'], oneline['save_time']))
    return oneline

def insert_a_record_tomysql(record) -> int:
    uuid = record['uuid']
    servername = record['unit']
    filename = record['filename']
    srcpath = record['srcpath']
    backup_dst = record['backup_dst']
    backup_remotedst = record['backup_remotedst']
    backup_period = record['backup_period']
    backup_volume = record['backup_volume']
    save_time = record['save_time']

    add_table_sql = "insert into backup.etc_backup values(\"%s\", \"%s\", \"%s\", \"%s\", \"%s\", \"%s\", \"%s\", \"%s\", \"%s\", \"%s\");" % (
    uuid, servername, filename, srcpath, backup_dst, backup_remotedst, datetime, backup_period, backup_volume, save_time)

    logging.info("add table sql is '%s'" % add_table_sql)
    password = get_value('conf', 'mysql_password')
    logging.debug("password is %s" % password)
    logging.info("mysql -u root -e '%s' -p%s > /dev/null" % (add_table_sql, password))
    return os.system("mysql -u root -e '%s' -p'%s' >/dev/null" % (add_table_sql, password))

def tar_to_somewhere(srcpath, dstpath) -> int:
    if os.path.isdir(srcpath):
        srcpath_s_dir = srcpath
    else:
        srcpath_s_dir = os.path.dirname(srcpath)
    with pushd(srcpath_s_dir):
        logging.debug("pushd in %s, now cwd is %s" % (srcpath_s_dir, os.getcwd()))
        if os.path.isdir(srcpath):
            logging.info("tar -czvf %s %s/*" % (dstpath, srcpath))
            tarres = os.system("tar -czvf %s ./*" % dstpath)
        else:
            logging.info("tar -czvf %s %s" % (dstpath, srcpath))
            tarres = os.system("tar -czvf %s %s" % (dstpath, os.path.basename(srcpath)))
    return tarres

def mylocal_to_somewhere():
    for key in dic.keys():
        logging.debug("key is %s" % key)
        if os.path.exists(key) == False:
            logging.warning("in mylocal_to_somewhere: %s is not exist, skip" % key)
            continue

        a_insert_record = get_a_insert_record(key)

        check_and_mkpath(a_insert_record['backup_dst'])

        tarres = tar_to_somewhere(key, a_insert_record['backup_dst'] + "/" + a_insert_record['filename']);
        if tarres == 0 or tarres == 1:
            if key == REDIS_TMP:
                a_insert_record['srcpath'] = 'redis'
            if insert_a_record_tomysql(a_insert_record) != 0:
                exit(1)

def myscp_to_somewhere():
    print("this is myscp_to_somewhere")


def myftp_to_somewhere():
    print("this is myftp_to_somewhere")

    ftp_ip = get_value('ftp', 'ip')
    remote_user = get_value('ftp', 'user')
    remote_password = get_value('ftp', 'password')
    logging.info("ip is %s, remote_user is %s, remote_password is %s" % (ftp_ip, remote_user, remote_password))

    with MyFTP(ftp_ip) as ftp:
        try:
            ftp.login(remote_user, remote_password)
            _myftp_to_somewhere(ftp)
        except ftplib.all_errors as e:
            logging.error("in myftp_to_somewhere: %s" %e)


def _myftp_to_somewhere(ftp):

    for key in dic.keys():
        logging.debug("key is %s" % key)
        if os.path.exists(key) == False:
            logging.warning("in mylocal_to_somewhere: %s is not exist, skip" % key)
            continue

        a_insert_record = get_a_insert_record(key)
        backup_remotedst = a_insert_record['backup_remotedst']
        if ftp.ftp_check_and_mkpath(backup_remotedst) != 0:
            logging.error("remote dstdir %s make failed, skip" % backup_remotedst)
            continue

        tmpdir = '/tmp/%s' % a_insert_record['unit']
        check_and_mkpath(tmpdir)
        os.system("rm -rf %s/*" % tmpdir)

        srcfilepath = tmpdir + "/" + a_insert_record['filename']
        tarres = tar_to_somewhere(key, srcfilepath)
        if tarres == 0 or tarres == 1:
            with open(srcfilepath, 'rb') as fp:
                res = ftp.storbinary("STOR " + backup_remotedst + "/" + a_insert_record['filename'], fp)
                if not res.startswith('226 Transfer complete'):
                    logging.error('%s Upload failed', srcfilepath)
                    continue
            if key == REDIS_TMP:
                a_insert_record['srcpath'] = 'redis'
            if insert_a_record_tomysql(a_insert_record) != 0:
                exit(1)
        else:
            logging.error("key %s not insert to database, skipped!" % key)

@contextlib.contextmanager
def DB(database, hostip, port, user, password):
    conn = pymysql.connect(host=hostip, port=3306, user=user, password=password, database=database, charset='gbk')
    cs = conn.cursor()

    yield conn, cs
    cs.close()
    conn.close()

def mysql_execute(sql) -> dict:
    password = get_value('conf', 'mysql_password')
    with DB(database=DATABASE_NAME, hostip='127.0.0.1', port=3306, user='root', password=password) as (conn, cs):
        cs.execute(sql)
        res = cs.fetchall()
        conn.commit()

    return res

def untar(srcpath, dstpath) -> bool:
    if os.path.isdir(dstpath) == True:
        if os.system("tar xvf %s -C %s" % (srcpath, dstpath)) == 2:
            return False
    else:
        if os.system("tar xvf %s -C %s" % (srcpath, os.path.dirname(dstpath))) == 2:
            return False
    return True


def restore_newest_local(path):
    t = mysql_execute("select srcpath, dstdir, remotedir, filename from backup.etc_backup where createtime"
                  " = (select createtime from backup.etc_backup where dstdir != '-' and createtime < NOW() limit 1);")

    prefix = get_value('restore', 'prefix')

    for key in t:
        print("key is", key)
        srcpath = key[0]

        if srcpath.startswith('/') == False:
            if srcpath == 'redis':
                srcpath = REDIS_TMP;
                logging.info("redis's srcpath is %s" % REDIS_TMP)
            else:
                logging.error("%s is not begin with '/', error restore, skip!" % srcpath)
                continue

        if prefix != '':
            srcpath = prefix + "/" + srcpath
            if os.path.isdir(srcpath) == True:
                check_and_mkpath(srcpath)
            else:
                check_and_mkpath(os.path.dirname(srcpath))

        dstdir = key[1]
        remotedir = key[2]
        filename = key[3]
        if remotedir != '-':
            logging.warning("restore in local, remotedst is not null, error, skip!")
            continue
        if untar(dstdir + "/" + filename, srcpath) == False:
            logging.error("%s restore fail, exit" % srcpath)
            exit(1)



def Backup():
    save_redis()
    create_mysql()
    add_dic_from_ini()

    opers = dict()
    opers['local'] = mylocal_to_somewhere
    opers['scp'] = myscp_to_somewhere
    opers['ftp'] = myftp_to_somewhere
    backup_type = get_value('backup', 'backup_type')
    if backup_type == '':
        logging.error("please ensure your backup_type!")
        exit(1)

    opers[backup_type]()

def Restore():
    logging.debug("will restore")

    restore_newest_local('/etc/neutron/')



if __name__ == "__main__":

    if os.getuid() != 0:
        logging.error("please use root privileges")
        exit(1)

    get_package('crudini', 'crudini')

    backup_or_restore = get_value('conf', 'backup_or_restore')
    if backup_or_restore == 'backup':
        Backup()
    elif backup_or_restore == 'restore':
        Restore()
    else:
        logging.error("It is neither a backup nor a restore. exit!")
        exit(1)

    logging.info("succeed, good bye")