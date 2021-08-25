#!/usr/bin/python3
import logging
logging.basicConfig(level=logging.DEBUG)
import time
import os
import sys
import string
import socket
global INI_FILE
INI_FILE = "backup.ini"
global REDIS_TMP
REDIS_TMP = "/tmp/redis-save"
dic = {}
daytime = time.strftime("%Y-%m-%d", time.localtime())
datetime = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())

print("daytime is ", daytime)
print("datetime is ", datetime)

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
    backup_type = get_value('conf', 'backup_type')
    logging.info("INIT DIC FROM INI")

    sections = get_section()
    for key in sections:
        logging.debug("now in add_dic_fomr_ini, key is %s" %key)
        src_path = unit = data_type = backup_dst = backup_remotedst = backup_period = backup_volume = save_time = ''
        if key == 'conf' or key == 'scp' or key == 'ftp':
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


def save_redis():
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

    a = os.system("redis-cli %s > /dev/null << EOF"
              "CONFIG SET dir %s \n"
              "SAVE \n"
"EOF" % (PASS, REDIS_TMP))
    if a == 0:
        logging.info("redis data save succeed...")
    else:
        logging.warning("redis data save failed!!!")
        return 1

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
    if os.system("mysql -u root -e %s -p%s &>/dev/null" % (create_table_sql, password)) != 0:
        exit(1)

def splice_tarfilename(servername, srcpath, data_type) -> string:
    _datetime = datetime.replace(' ', '_')
    srcpath_changed = srcpath.replace('/', '_')

    filename = socket.gethostname().join('_').join(_datetime).join('_').join(servername)
    while filename[-1] == '_':
        filename=filename[:-1]
    filename.join(srcpath_changed)
    while filename[-1] == '_':
        filename=filename[:-1]
    filename.join('_').join(data_type).join('.tar.gz')

    return filename

def mytar_to_somewhere():
    for key in dic.keys():
        logging.debug("key is %s" % key)
        srcpath = key
        servername = dic[key]['unit']
        data_type = dic[key]['data_type']
        backup_dst = dic[key]['backup_dst']
        backup_remotedst = dic[key]['backup_remotedst']
        backup_period = dic[key]['backup_period']
        backup_volume = dic[key]['backup_volume']
        save_time = dic[key]['save_time']

        logging.debug("servername: %s, data_type: %s, backup_dst: %s, backup_remotedst: %s, backup_period: %s, "
                      "backup_volume: %s, save_time: %s" % (servername, data_type, backup_dst, backup_remotedst,
                                                            backup_period,backup_volume, save_time))
        uuid = os.popen("uuidgen").read().strip('\n')
        filename = splice_tarfilename(servername, srcpath, data_type)
        if os.path.exists(srcpath) == False:
            logging.warning("in mytar_to_somewhere: %s is not exist, skip" % srcpath)
            continue

        check_and_mkpath(backup_dst)

        if os.path.isdir(srcpath):
            os.system("pushd %s > /dev/null" % srcpath)
            logging.info("tar -czvf %s/%s %s/*" % (backup_dst, filename, srcpath))
            tarres = os.system("tar -czvf %s/%s %s/*" % (backup_dst, filename, srcpath))
        else:
            os.system("pushd %s/.. > /dev/null" % srcpath)
            logging.info("tar -czvf %s/%s %s" % (backup_dst, filename, srcpath))
            tarres = os.system("tar -czvf %s/%s %s" % (backup_dst, filename, srcpath))
        if tarres == 0 or tarres == 1:
            if srcpath == REDIS_TMP:
                srcpath = 'redis'
            add_table_sql = "insert into backup.etc_backup values(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s);" % (uuid, servername,
                filename, srcpath, backup_dst, backup_remotedst, datetime, backup_period, backup_volume, save_time)
            logging.info("add table sql is %s" % add_table_sql)
            if os.system("mysql -u root -e %s -p %s >/dev/null") == False:
                exit(1)
        os.system("popd > /dev/null")


if __name__ == "__main__":
    install = get_installcmd()
    print("APT is %s" %install)

    # get_package('haha', 'haha')

    backup_or_restore = get_value('conf', 'backup_or_restore')
    print("backup_or_restore is ", backup_or_restore)

    sections = get_section()
    print("sections is ", sections)

    print("add_dic_from_ini")
    add_dic_from_ini()

    print(str(dic))

    save_redis()

#    for key in dic.items():
#        print("%s: " %key)
    mytar_to_somewhere()
