#!/usr/bin/env python3
import logging
logging.basicConfig(level=logging.INFO)
import time
import os
import string
import socket
import contextlib
import ftplib
import pymysql
from apscheduler.schedulers.blocking import BlockingScheduler

INI_FILE = os.getcwd() + '/backup.ini'
REDIS_TMP = '/tmp/redis-save'
DATABASE_NAME = 'backup_database'
TABLE_NAME = 'backup_table'
dic = {}

def get_value(section, key):
    res = os.popen("crudini --get %s %s %s 2>/dev/null" %(INI_FILE, section, key)).read().strip('\n')
    return res


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

def less_debug() -> bool:
    if logging.getLogger().level <= logging.DEBUG:
        return True
    return False

def get_installcmd() -> str:
    os_VENDOR = os.popen("lsb_release -i -s").read().strip('\n')
    logging.info("os_VENDOR is %s" % os_VENDOR)
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
            logging.critical("%s is install failed" %package)
            exit(1)


def get_section():
    return get_value('', '').split('\n')

def check_and_mkpath(dir) -> bool:
    if os.path.exists(dir) and os.path.isdir(dir) == False:
        logging.error("%s is exist but not a dir" %dir)
        return False
    if os.path.exists(dir) == False:
        logging.debug("mkdir %s" %dir)
        try:
            os.system("mkdir %s -p" %dir)
        except:
            return False
    return True

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
                logging.critical("%s is not begin with / , and it is no redis, exit!")
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
        backup_clocktime = get_value(key, 'backup_clocktime')
        backup_volume = get_value(key, 'backup_volume')
        save_time = get_value(key, 'save_time')

        if backup_dst == '' and backup_type == 'local':
            logging.error("get_value %s backup_dstdir is null, skip!" %key)
            continue
        if backup_remotedst == '' and (backup_type == 'scp' or backup_type == 'ftp'):
            logging.error("get_value %s remote_dstdir is null, skip!" %key)
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
            'backup_clocktime': backup_clocktime,
            'backup_volume': backup_volume,
            'save_time': save_time
        }
    logging.info("INIT DIC FROM INI END")


def save_redis() -> bool:
    redis_values = get_value('redis', '').split('\n')
    logging.debug("redis_values is %s" % redis_values)
    if not redis_values:
        logging.warning("ini has no redis, skip to save it")
        return False
    check_and_mkpath(REDIS_TMP)
    os.system("rm -rf %s/*" % REDIS_TMP)

    if os.system("redis-cli CONFIG GET dir > /dev/null") != 0:
        logging.error("exit from save_redis")
        return False

    if os.system("redis-cli CONFIG GET dir | grep \"NOAUTH Authentication required\"") == 0:
        password = get_value('redis', 'server-password')
        if password == '':
            exit(1)
        PASS = "-a %s" %password
    else:
        PASS = ''
    logging.debug("PASS is %s" % PASS)

    if os.system("redis-cli %s CONFIG SET dir %s > /dev/null" % (PASS, REDIS_TMP)) != 0:
        return False
    if os.system("redis-cli SAVE > /dev/null") != 0:
        logging.error("redis data save failed!!!")
        return False
    logging.info("redis data save succeed...")
    return True

def mysql_execute(sql) -> bool:
    mysql_username = get_value('conf', 'mysql_username')
    mysql_password = get_value('conf', 'mysql_password')
    logging.debug("mysql -u %s -e '%s' -p'%s' >/dev/null" % (mysql_username, sql, mysql_password))
    if os.system("mysql -u %s -e '%s' -p'%s' >/dev/null" % (mysql_username, sql, mysql_password)) != 0:
        return False
    return True

def create_mysql():
    create_database_sql = "CREATE DATABASE IF NOT EXISTS {}".format(DATABASE_NAME)
    if mysql_execute(create_database_sql) == False:
        exit(1)

    create_table_sql = "CREATE TABLE IF NOT EXISTS {}.{} (" \
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
                        "UNIQUE INDEX uuid_etc_bakup_UNIQUE(uuid ASC) VISIBLE);".format(DATABASE_NAME, TABLE_NAME)

    if mysql_execute(create_table_sql) == False:
        exit(1)

def splice_tarfilename(datetime, servername, srcpath, data_type) -> str:
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
    oneline['backup_clocktime'] = dic[key]['backup_clocktime']
    oneline['backup_volume'] = dic[key]['backup_volume']
    oneline['save_time'] = dic[key]['save_time']
    oneline['uuid'] = os.popen("uuidgen").read().strip('\n')
    oneline['datetime'] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    oneline['filename'] = splice_tarfilename(oneline['datetime'], oneline['unit'], oneline['srcpath'], oneline['data_type'])
    logging.debug("srcpath: %s, unit: %s, data_type: %s, backup_dst: %s, backup_remotedst: %s, backup_period: %s, "
                  "backup_volume: %s, save_time: %s" % (oneline['srcpath'], oneline['unit'], oneline['data_type'], oneline['backup_dst'],
                    oneline['backup_remotedst'], oneline['backup_period'], oneline['backup_volume'], oneline['save_time']))
    return oneline

def insert_a_record_tomysql(record) -> bool:
    uuid = record['uuid']
    datetime = record['datetime']
    servername = record['unit']
    filename = record['filename']
    srcpath = record['srcpath']
    backup_dst = record['backup_dst']
    backup_remotedst = record['backup_remotedst']
    backup_period = record['backup_period']
    backup_volume = record['backup_volume']
    save_time = record['save_time']

    add_table_sql = "insert into %s.%s values(\"%s\", \"%s\", \"%s\", \"%s\", \"%s\", \"%s\", \"%s\", \"%s\", \"%s\", \"%s\");" % (
    DATABASE_NAME, TABLE_NAME, uuid, servername, filename, srcpath, backup_dst, backup_remotedst, datetime, backup_period, backup_volume, save_time)

    logging.debug("add table sql is '%s'" % add_table_sql)
    if mysql_execute(add_table_sql) == False:
        return False
    return True

def tar_to_somewhere(srcpath, dstpath) -> bool:
    if os.path.isdir(srcpath):
        srcpath_s_dir = srcpath
        if not os.listdir(srcpath):
            return False
    else:
        srcpath_s_dir = os.path.dirname(srcpath)

    with pushd(srcpath_s_dir):
        logging.debug("pushd in %s, now cwd is %s" % (srcpath_s_dir, os.getcwd()))
        try:
            if os.path.isdir(srcpath):
                logging.info("tar -czvf %s %s/*" % (dstpath, srcpath))
                if less_debug():
                    tarres = os.system("tar -czvf %s ./*" % dstpath)
                else:
                    tarres = os.system("tar -czvf %s ./* >/dev/null 2>&1" % dstpath)
            else:
                logging.info("tar -czvf %s %s" % (dstpath, srcpath))
                if less_debug():
                    tarres = os.system("tar -czvf %s %s" % (dstpath, os.path.basename(srcpath)))
                else:
                    tarres = os.system("tar -czvf %s %s >/dev/null 2>&1" % (dstpath, os.path.basename(srcpath)))
        except Exception as e:
            logging.error("in tar_to_somewhere: %s" % e)
            return False

    if tarres == 2:
        return False
    return True


def mylocal_to_somewhere_onesrcpath(srcpath) -> bool:
    if os.path.exists(srcpath) == False:
        logging.error("in mylocal_to_somewhere_*: %s is not exist, failed to backup" % srcpath)
        return False
    a_insert_record = get_a_insert_record(srcpath)

    daytime = time.strftime("%Y-%m-%d", time.strptime(a_insert_record['datetime'], "%Y-%m-%d %H:%M:%S"))
    check_and_mkpath(a_insert_record['backup_dst'] + "/" + daytime)

    tarres = tar_to_somewhere(srcpath, a_insert_record['backup_dst'] + "/" + daytime + "/" + a_insert_record['filename'])
    # if tarres == 0 or tarres == 1:
    if tarres == False:
        return False
    if srcpath == REDIS_TMP:
        a_insert_record['srcpath'] = 'redis'
    if insert_a_record_tomysql(a_insert_record) == False:
        return False
    return True


def mylocal_to_somewhere_all():
    scheduler = BlockingScheduler()
    for key in dic.keys():
        logging.debug("key is %s" % key)
        backup_period = dic[key]['backup_period']
        backup_clocktime = dic[key]['backup_clocktime']

        if backup_period == '':
            backup_period = 7

        def is_valid_clocktime(str):
            try:
                time.strptime(str, "%H:%M:%S")
                return True
            except:
                return False
        if backup_clocktime == '':
            scheduler.add_job(mylocal_to_somewhere_onesrcpath, 'interval', days=int(backup_period), args=[key])
        elif is_valid_clocktime(backup_clocktime):
            hour = time.strftime("%H", time.strptime(backup_clocktime, "%H:%M:%S"))
            minute = time.strftime("%M", time.strptime(backup_clocktime, "%H:%M:%S"))
            second = time.strftime("%S", time.strptime(backup_clocktime, "%H:%M:%S"))
            scheduler.add_job(mylocal_to_somewhere_onesrcpath, 'cron', day=backup_period, hour=hour, minute=minute, second=second, args=[key])
        else:
            logging.critical("backup_clocktime %s in section %s is invaild!" % (backup_clocktime, key))
            exit(1)
        mylocal_to_somewhere_onesrcpath(key)
    scheduler.start()

def mylocal_to_somewhere():
    srcpath = get_value('backup', 'srcpath')
    if srcpath == '':
        mylocal_to_somewhere_all()
    else:
        mylocal_to_somewhere_onesrcpath(srcpath)

def myscp_to_somewhere():
    logging.debug("this is myscp_to_somewhere")


def myftp_to_somewhere():
    logging.debug("this is myftp_to_somewhere")
    srcpath = get_value('backup', 'srcpath')
    if srcpath == '':
        myftp_to_somewhere_all()
    else:
        myftp_to_somewhere_onesrcpath(srcpath)

def myftp_to_somewhere_onesrcpath(srcpath) -> bool:
    ftp_ip = get_value('ftp', 'ip')
    remote_user = get_value('ftp', 'user')
    remote_password = get_value('ftp', 'password')
    logging.debug("ip is %s, remote_user is %s, remote_password is %s" % (ftp_ip, remote_user, remote_password))

    with MyFTP(ftp_ip) as ftp:
        try:
            ftp.login(remote_user, remote_password)
            _myftp_to_somewhere_onesrcpath(ftp, srcpath)
        except ftplib.all_errors as e:
            logging.error("in myftp_to_somewhere: %s" %e)

def _myftp_to_somewhere_onesrcpath(ftp, srcpath) -> bool:
    if os.path.exists(srcpath) == False:
        logging.error("in myftp_to_somewhere_*: %s is not exist, failed to backup" % srcpath)
        return False
    a_insert_record = get_a_insert_record(srcpath)

    backup_remotedst = a_insert_record['backup_remotedst']
    daytime = time.strftime("%Y-%m-%d", time.strptime(a_insert_record['datetime'], "%Y-%m-%d %H:%M:%S"))
    if ftp.ftp_check_and_mkpath(backup_remotedst + "/" + daytime) != 0:
        logging.error("remote dstdir %s make failed, failed to backup %s" % (backup_remotedst, srcpath))
        return False

    tmpdir = '/tmp/%s' % a_insert_record['unit']
    check_and_mkpath(tmpdir)
    os.system("rm -rf %s/*" % tmpdir)

    srcfilepath = tmpdir + "/" + a_insert_record['filename']
    tarres = tar_to_somewhere(srcpath, srcfilepath)
    # if tarres == 0 or tarres == 1:
    if tarres == True:
        with open(srcfilepath, 'rb') as fp:
            res = ftp.storbinary("STOR " + backup_remotedst + "/" + daytime + "/" + a_insert_record['filename'], fp)
            if not res.startswith('226 Transfer complete'):
                logging.error('%s Upload failed', srcfilepath)
                return False
        if srcpath == REDIS_TMP:
            a_insert_record['srcpath'] = 'redis'
        if insert_a_record_tomysql(a_insert_record) == False:
            return False
    else:
        return False

def myftp_to_somewhere_all():
    scheduler = BlockingScheduler()
    for key in dic.keys():
        logging.debug("key is %s" % key)
        backup_period = dic[key]['backup_period']
        backup_clocktime = dic[key]['backup_clocktime']

        if backup_period == '':
            backup_period = 7

        def is_valid_clocktime(str):
            try:
                time.strptime(str, "%H:%M:%S")
                return True
            except:
                return False
        if backup_clocktime == '':
            scheduler.add_job(myftp_to_somewhere_onesrcpath, 'interval', days=int(backup_period), args=[key])
            #scheduler.add_job(myftp_to_somewhere_onesrcpath, 'interval', minutes=2, args=[key])
        elif is_valid_clocktime(backup_clocktime):
            hour = time.strftime("%H", time.strptime(backup_clocktime, "%H:%M:%S"))
            minute = time.strftime("%M", time.strptime(backup_clocktime, "%H:%M:%S"))
            second = time.strftime("%S", time.strptime(backup_clocktime, "%H:%M:%S"))
            scheduler.add_job(myftp_to_somewhere_onesrcpath, 'cron', day=backup_period, hour=hour, minute=minute, second=second, args=[key])
        else:
            logging.critical("backup_clocktime %s in section %s is invaild!" % (backup_clocktime, key))
            exit(1)
        myftp_to_somewhere_onesrcpath(key)
    scheduler.start()

@contextlib.contextmanager
def DB(database, hostip, port, user, password):
    conn = pymysql.connect(host=hostip, port=3306, user=user, password=password, database=database, charset='gbk')
    cs = conn.cursor()

    yield conn, cs
    cs.close()
    conn.close()

def mysql_execute(sql) -> dict:
    username = get_value('conf', 'mysql_username')
    password = get_value('conf', 'mysql_password')
    try:
        with DB(database=DATABASE_NAME, hostip='127.0.0.1', port=3306, user=username, password=password) as (conn, cs):
            cs.execute(sql)
            res = cs.fetchall()
            conn.commit()
    except pymysql.err.Error as e:
        logging.error(e)
        exit(1)
    logging.debug("sql: the result of %s is:" % sql)
    for i in res:
        logging.debug(i)
    return res

def untar(srcpath, dstpath) -> bool:
    if os.path.exists(srcpath) == False:
        logging.error("%s is not exist" %srcpath)
        return False
    try:
        if os.path.isdir(dstpath) == True:
            logging.info("tar xvf %s -C %s" % (srcpath, dstpath))
            if less_debug():
                tarres = os.system("tar xvf %s -C %s" % (srcpath, dstpath))
            else:
                tarres = os.system("tar xvf %s -C %s >/dev/null 2>&1" % (srcpath, dstpath))
        else:
            if os.path.exists(os.path.dirname(dstpath)) == False:
                logging.error("%s is not exist" % os.path.dirname(dstpath))
                return False
            logging.info("tar xvf %s -C %s" % (srcpath, os.path.dirname(dstpath)))
            if less_debug():
                tarres = os.system("tar xvf %s -C %s" % (srcpath, os.path.dirname(dstpath)))
            else:
                tarres = os.system("tar xvf %s -C %s >/dev/null 2>&1" % (srcpath, os.path.dirname(dstpath)))
    except Exception as e:
        logging.error("in untar: %s" % e)
        return False
    if tarres == 2:
        return False
    return True

def restore_local_onesrcpath(srcpath_dstdir_remotedir_daytime_filename_tuple) -> bool:
    prefix = get_value('restore', 'prefix')
    srcpath = srcpath_dstdir_remotedir_daytime_filename_tuple[0]
    dstdir = srcpath_dstdir_remotedir_daytime_filename_tuple[1]
    remotedir = srcpath_dstdir_remotedir_daytime_filename_tuple[2]
    daytime = srcpath_dstdir_remotedir_daytime_filename_tuple[3]
    filename = srcpath_dstdir_remotedir_daytime_filename_tuple[4]

    if srcpath.startswith('/') == False:
        if srcpath == 'redis':
            srcpath = REDIS_TMP;
            logging.debug("redis's srcpath is %s" % REDIS_TMP)
        else:
            logging.error("%s is not begin with '/', error restore!" % srcpath)
            return False
    if prefix != '':
        srcpath = prefix + "/" + srcpath
        if os.path.isdir(srcpath) == True:
            check_and_mkpath(srcpath)
        else:
            check_and_mkpath(os.path.dirname(srcpath))

    if remotedir != '-':
        logging.error("restore in local, remotedir is not null, error")
        return False

    if untar(dstdir + "/" + daytime + "/" + filename, srcpath) == False:
        logging.error("%s untar error, restore fail" % srcpath)
        return False
    logging.info("restore_local_onesrcpath %s success" % srcpath)
    return True

def restore_newest_local_all():
    sections = get_section()
    for key in sections:
        if key == 'conf' or key == 'scp' or key == 'ftp' or key == 'backup' or key == 'restore':
            continue
        t = mysql_execute("select srcpath, dstdir, remotedir, DATE_FORMAT(createtime, '%Y-%m-%d'), filename from {0}.{1} where "
                          "srcpath = '{2}' and dstdir != '-' order by createtime desc limit 1;".format(DATABASE_NAME, TABLE_NAME, key))
        if not t:
            logging.error("select srcpath: %s, but there is not a valid record" % (key))
            continue
        restore_local_onesrcpath(t[0])

def restore_by_createtime_local_all(createtime):
    sections = get_section()
    for key in sections:
        if key == 'conf' or key == 'scp' or key == 'ftp' or key == 'backup' or key == 'restore':
            continue
        t = mysql_execute("select srcpath, dstdir, remotedir, DATE_FORMAT(createtime, '%Y-%m-%d'), filename from {0}.{1} where dstdir != '-' and createtime = '{2}' "
                          "and srcpath = '{3}';".format(DATABASE_NAME, TABLE_NAME, createtime, key))
        if not t:
            logging.error("select srcpath: %s, createtime: %s, but there is not a valid record" % (key, createtime))
            continue
        restore_local_onesrcpath(t[0])

def restore_by_createday_local(createday):
    createday_format = time.strftime("%Y-%m-%d", time.strptime(createday, "%Y-%m-%d"))

    t = mysql_execute("select DATE_FORMAT(createtime, '%Y-%m-%d') from {}.{};".format(DATABASE_NAME, TABLE_NAME))
    flag = 1
    for i in t:
        if createday_format == i[0]:
            flag = 0
            break
        flag = 1
    if flag == 1:
        logging.critical("there is not a valid record")
        exit(1)

    sections = get_section()
    for key in sections:
        if key == 'conf' or key == 'scp' or key == 'ftp' or key == 'backup' or key == 'restore':
            continue
        t = mysql_execute("select srcpath, dstdir, remotedir, DATE_FORMAT(createtime, '%Y-%m-%d'), filename from {0}.{1} where createtime"
                      " = (select createtime from {0}.{1} where dstdir != '-' and createtime like '{2}%' and srcpath = '{3}' "
                      "order by createtime desc limit 1);".format(DATABASE_NAME, TABLE_NAME, createday_format, key))
        if not t:
            logging.error("select srcpath: %s, createday: %s, but there is not a valid record" % (key, createday))
            continue
        restore_local_onesrcpath(t[0])

def restore_ftp_onesrcpath(srcpath_dstdir_remotedir_daytime_filename_servername_tuple) -> bool:
    ftp_ip = get_value('ftp', 'ip')
    remote_user = get_value('ftp', 'user')
    remote_password = get_value('ftp', 'password')
    logging.debug("ip is %s, remote_user is %s, remote_password is %s" % (ftp_ip, remote_user, remote_password))

    with MyFTP(ftp_ip) as ftp:
        try:
            ftp.login(remote_user, remote_password)
            _restore_ftp_onesrcpath(ftp, srcpath_dstdir_remotedir_daytime_filename_servername_tuple)
        except ftplib.all_errors as e:
            logging.error("in restore_ftp_onesrcpath: %s" % e)

def _restore_ftp_onesrcpath(ftp, srcpath_dstdir_remotedir_daytime_filename_servername_tuple) -> bool:
    prefix = get_value('restore', 'prefix')
    srcpath = srcpath_dstdir_remotedir_daytime_filename_servername_tuple[0]
    dstdir = srcpath_dstdir_remotedir_daytime_filename_servername_tuple[1]
    remotedir = srcpath_dstdir_remotedir_daytime_filename_servername_tuple[2]
    daytime = srcpath_dstdir_remotedir_daytime_filename_servername_tuple[3]
    filename = srcpath_dstdir_remotedir_daytime_filename_servername_tuple[4]
    servername = srcpath_dstdir_remotedir_daytime_filename_servername_tuple[5]

    if srcpath.startswith('/') == False:
        if srcpath == 'redis':
            srcpath = REDIS_TMP;
            logging.info("redis's srcpath is %s" % REDIS_TMP)
        else:
            logging.error("%s is not begin with '/', error restore, skip!" % srcpath)
            return False

    if prefix != '':
        srcpath = prefix + "/" + srcpath
        if os.path.isdir(srcpath) == True:
            check_and_mkpath(srcpath)
        else:
            check_and_mkpath(os.path.dirname(srcpath))

    tmpdir = '/tmp/%s' % servername
    check_and_mkpath(tmpdir)
    os.system("rm -rf %s/*" % tmpdir)

    if dstdir != '-':
        logging.warning("restore in ftp, dstdir is not null, error, skip!")
        return False

    try:
        with open(tmpdir + "/" + filename, 'wb') as fp:
            res = ftp.retrbinary('RETR ' + remotedir + '/' + daytime + '/' + filename, fp.write)
            if not res.startswith('226 Transfer complete'):
                logging.error('Downlaod %s/%s failed' % (tmpdir, filename))
                if os.path.isfile(tmpdir + "/" + filename):
                    os.remove(tmpdir + "/" + filename)
    except ftplib.all_errors as e:
        logging.error("FTP error: %s" % e)
        if os.path.isfile(tmpdir + "/" + filename):
            os.remove(tmpdir + "/" + filename)
            return False

    if untar(tmpdir + "/" + filename, srcpath) == False:
        logging.error("%s restore fail, exit" % srcpath)
        logging.error("%s/%s untar error, restore fail" % (tmpdir, filename))
        return False
    logging.info("restore_ftp_onesrcpath %s success" % srcpath)
    return True

def restore_newest_ftp_all():
    sections = get_section()
    for key in sections:
        if key == 'conf' or key == 'scp' or key == 'ftp' or key == 'backup' or key == 'restore':
            continue
        t = mysql_execute(
            "select srcpath, dstdir, remotedir, DATE_FORMAT(createtime, '%Y-%m-%d'), filename, servername from {0}.{1} where "
            "srcpath = '{2}' and remotedir != '-' order by createtime desc limit 1;".format(DATABASE_NAME, TABLE_NAME, key))
        if not t:
            logging.error("select srcpath: %s, but there is not a valid record" % (key))
            continue
        restore_ftp_onesrcpath(t[0])

def restore_by_createtime_ftp_all(createtime):
    sections = get_section()
    for key in sections:
        if key == 'conf' or key == 'scp' or key == 'ftp' or key == 'backup' or key == 'restore':
            continue
        t = mysql_execute(
            "select srcpath, dstdir, remotedir, DATE_FORMAT(createtime, '%Y-%m-%d'), filename, servername from {0}.{1} where remotedir != '-' and createtime = '{2}' "
            "and srcpath = '{3}';".format(DATABASE_NAME, TABLE_NAME, createtime, key))
        if not t:
            logging.error("select srcpath: %s, createtime: %s, but there is not a valid record" % (key, createtime))
            continue
        restore_ftp_onesrcpath(t[0])

def restore_by_createday_ftp_all(createday):
    createday_format = time.strftime("%Y-%m-%d", time.strptime(createday, "%Y-%m-%d"))

    t = mysql_execute("select DATE_FORMAT(createtime, '%Y-%m-%d') from {}.{};".format(DATABASE_NAME, TABLE_NAME))
    flag = 1
    for i in t:
        if createday_format == i[0]:
            flag = 0
            break
        flag = 1
    if flag == 1:
        logging.critical("there is not a valid record")
        exit(1)

    sections = get_section()
    for key in sections:
        if key == 'conf' or key == 'scp' or key == 'ftp' or key == 'backup' or key == 'restore':
            continue
        t = mysql_execute(
            "select srcpath, dstdir, remotedir, DATE_FORMAT(createtime, '%Y-%m-%d'), filename, servername from {0}.{1} where createtime"
            " = (select createtime from {0}.{1} where remotedir != '-' and createtime like '{2}%' and srcpath = '{3}' "
            "order by createtime desc limit 1);".format(DATABASE_NAME, TABLE_NAME, createday_format, key))
        if not t:
            logging.error("select srcpath: %s, createday: %s, but there is not a valid record" % (key, createday))
            continue
        restore_ftp_onesrcpath(t[0])


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
        logging.critical("please ensure your backup_type!")
        exit(1)

    opers[backup_type]()
    logging.info("succeed, good bye")


def Restore():
    logging.debug("will restore")

    restore_type = get_value('restore', 'restore_type')
    restore_time = get_value('restore', 'restore_time')
    def is_valid_day(str):
        try:
            time.strptime(str, '%Y-%m-%d')
            return True
        except:
            return False
    if restore_type == 'local':
        if restore_time == '':
            restore_newest_local_all()
        elif is_valid_day(restore_time):
            restore_by_createday_local(restore_time)
        else:
            restore_by_createtime_local_all(restore_time)
    elif restore_type == 'ftp':
        if restore_time == '':
            restore_newest_ftp_all()
        elif is_valid_day(restore_time):
            restore_by_createday_ftp_all(restore_time)
        else:
            restore_by_createtime_ftp_all(restore_time)
    else:
        logging.critical("please ensure your restore_type")
        exit(1)


if __name__ == "__main__":

    if os.getuid() != 0:
        logging.critical("please use root privileges")
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
