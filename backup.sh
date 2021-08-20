#!/bin/bash

INI_FILE=test.ini

datetime=`date +%Y-%m-%d`
datetime_tosql=`date "+%Y-%m-%d %H:%M:%S"`

declare -g password APT

get_ostype() {
	local os_VENDOR=$(lsb_release -i -s)

	if [[ $os_VENDOR =~ (Debian|Ubuntu|LinuxMint) ]]; then
		APT=apt
	else
		APT=dnf
	fi

}

get_package() {
	get_ostype
	local cmd=$1
	local package=$2
	which $1
	if [ $? -ne 0 ]; then
		${APT} install $2 -y
		if [ $? -ne 0 ]; then
        		echo "$2 is install failed!";
			exit 1
		fi
	fi
}


check_and_mkpath() {
	local dir=$1
	if [ -e $dir -a ! -d $dir ]; then
        	echo "$dir is exist but not a dir";
		exit 1
	fi
	[ -d $dir ] || (echo "mkdir $dir";mkdir $dir -p)

}

declare -A dic

init_dic() {
	NOVA="nova"
	NEUTRON="neutron"
	CINDER="cinder"
	CEILOMETER="ceilometer"
	LOG="log"
	
	ETC_NOVA="/etc/nova"
	ETC_NEUTRON="/etc/neutron"
	ETC_CINDER="/etc/cinder"
	ETC_CEILOMETER="/etc/ceilometer"
	VAR_LOG="/var/log"

	dic=(
        	#[${NOVA}]=	'$ETC_NOVA               $BAK_NOVA       每周备份一次    52      12'
        	#[${NEUTRON}]=	'$ETC_NEUTRON            $BAK_NEUTRON    每周备份一次    24      12'
        	#[${CINDER}]=	'$ETC_CINDER             $BAK_CINDER     每周备份一次    56      12'
        	#[${CEILOMETER}]='$ETC_CEILOMETER         $BAK_CEILOMETER 每周备份一次    56      12'
        	#[${LOG}]=	'$VAR_LOG		 $BAK_LOG        每周备份一次    56      12'
		[${NOVA}]="$ETC_NOVA"
        	[${NEUTRON}]="$ETC_NEUTRON"
        	[${CINDER}]="$ETC_CINDER"
        	[${CEILOMETER}]="$ETC_CEILOMETER"
        	[${LOG}]="$VAR_LOG"
	)
}

add_dic_from_ini() {
	for key in ${!dic[*]}; do
		echo "oneline is ${dic[$key]}"
		backup_dst=`crudini --get ${INI_FILE} $key backup_dstdir`
		backup_remotedst=`crudini --get ${INI_FILE} $key remote_dstdir`
		backup_period=`crudini --get ${INI_FILE} $key backup_period`
		backup_volume=`crudini --get ${INI_FILE} $key backup_volume`
		save_time=`crudini --get ${INI_FILE} $key save_time`
		dic[$key]+=" $backup_dst $backup_remotedst $backup_period $backup_volume $save_time"
		echo "dic[key] = ${dic[$key]}"
	done
}


create_mysql() {
	CREATE_DATABASE_SQL="CREATE DATABASE IF NOT EXISTS backup"

	CREATE_TABLE_SQL="CREATE TABLE IF NOT EXISTS backup.etc_backup (
  				uuid VARCHAR(45) NOT NULL,
  				servername VARCHAR(45) NOT NULL,
  				filename VARCHAR(1024) NOT NULL,
  				srcpath VARCHAR(1024) NOT NULL,
  				dstdir VARCHAR(1024) NOT NULL,
  				remotedir VARCHAR(1024) NOT NULL,
  				createtime DATETIME NOT NULL,
  				backup_per VARCHAR(45) NOT NULL,
				backup_sto VARCHAR(45) NOT NULL,
				save_time VARCHAR(45) NOT NULL,
  				PRIMARY KEY (uuid),
  				UNIQUE INDEX uuid_etc_bakup_UNIQUE (uuid ASC) VISIBLE);"
	mysql -u root -e "${CREATE_TABLE_SQL}" -p$password
	if [ $? -ne 0 ]; then
		exit 1
	fi
}

mytar_to_somewhere() {
	local key=$1
	local oneline=(${dic[$key]})
	local servername=$key
	local srcpath=${oneline[0]}
	local dstdir=${oneline[1]}/$datetime
	local backup_per=${oneline[3]}
	local backup_sto=${oneline[4]}
	local save_time=${oneline[5]}

	local uuid=`uuidgen`

	local _datetime=${datetime_tosql/ /_}
	local filename=`hostname`_${_datetime}_${servername}_conf.tar.gz

	if [ ! -d $srcpath ]; then
		echo "$srcpath is not exist, skip"
		return
	fi

	check_and_mkpath $dstdir

	pushd $srcpath
	echo "tar -czvf $dstdir/$filename $srcpath/*"
	tar -czvf $dstdir/$filename ./*
	if [ $? -eq 0 -o $? -eq 1 ]; then

		ADD_TABLE_SQL="insert into backup.etc_backup values(\"$uuid\", \"$servername\", \"$filename\", \"$srcpath\", \"$dstdir\", \"$remote_dstdir\", \"${datetime_tosql}\", \"$backup_per\", \"$backup_sto\", \"$save_time\");"	
		echo "ADD_TABLE_SQL is $ADD_TABLE_SQL"
		mysql -u root -e "${ADD_TABLE_SQL}" -p$password
		if [ $? -ne 0 ]; then
			exit 1
		fi

	fi
	popd
}

scp_expect() {
	local filepath=$1
	local user=$2
	local ip=$3
	local password=$4
	local dstdir=$5

	expect << EOF
	set timeout 30
    	spawn scp -r $filepath ${user}@${ip}:${dstdir}
    	expect { 
        	"yes/no" { send "yes\n";exp_continue } 
        	"password" { send "$password\n" }
    	} 	
	expect eof
	catch wait result
        exit [lindex \$result 3]
EOF
}

check_and_mkpath_ssh() {
	local dir=$1
	local user=$2
	local ip=$3
	local password=$4

	expect << EOF
	set timeout 30
    	spawn ssh ${user}@${ip}
    	expect { 
        	"yes/no" { send "yes\n";exp_continue } 
        	"password" { send "$password\n" }
    	} 	
	expect "]#" {send "if \[ ! -e $dir \]; then mkdir $dir -p; fi\n"}
	send "exit\n"
	expect eof
	catch wait result
        exit [lindex \$result 3]
EOF

}


myscp_to_somewhere() {
	echo "this is myscp_to_somewhere"

	local key=$1
	local oneline=(${dic[$key]})
	local servername=$key
	local srcpath=${oneline[0]}
	local remote_dstdir=${oneline[2]}/$datetime
	local backup_per=${oneline[3]}
	local backup_sto=${oneline[4]}
	local save_time=${oneline[5]}


	local uuid=`uuidgen`
	local _datetime=${datetime_tosql/ /_}
	local filename=`hostname`_${_datetime}_${servername}_conf.tar.gz

	if [ ! -d $srcpath ]; then
		echo "$srcpath is not exist, skip"
		return
	fi


	local ip=`crudini --get ${INI_FILE} scp ip`
	local remote_user=`crudini --get ${INI_FILE} scp user`
	local remote_password=`crudini --get ${INI_FILE} scp password`
	echo "ip is $ip"
	echo "remote_user is ${remote_user}"
	echo "remote_password is ${remote_password}"
	echo "remote_dstdir is ${remote_dstdir}"

	check_and_mkpath_ssh $remote_dstdir $remote_user $ip $remote_password

	local tmpdir="/tmp/$servername"
	check_and_mkpath $tmpdir
	rm -rf $tmpdir/*

	pushd $srcpath
	echo "tar -czvf $tmpdir/$filename $srcpath/*"
	tar -czvf $tmpdir/$filename ./*
	if [ $? -eq 0 -o $? -eq 1 ]; then

		echo "scp $tmpdir/$filename $remote_user $ip $remote_password $remote_dstdir"
		scp_expect $tmpdir/$filename $remote_user $ip $remote_password $remote_dstdir 
		if [ $? -eq 0 ]; then
			ADD_TABLE_SQL="insert into backup.etc_backup values(\"$uuid\", \"$servername\", \"$filename\", \"$srcpath\", \"$dstdir\", \"${remote_dstdir}\", \"${datetime_tosql}\", \"$backup_per\", \"$backup_sto\", \"$save_time\");"	
			echo "ADD_TABLE_SQL is $ADD_TABLE_SQL"
			mysql -u root -e "${ADD_TABLE_SQL}" -p$password
			if [ $? -ne 0 ]; then
				exit 1
			fi
		else
			echo "not insert to database, skipped!"
		fi

	fi
	popd

}

#check_and_mkpath_ftp 192.168.40.130 bobbi qwer1234 /shell
check_and_mkpath_ftp() {
        local ip=$1
        local user=$2
        local password=$3
        local dstdir=$4

        lftp -u ${user},${password} -p 21 ftp://${ip} > /dev/null 2>&1 << EOF
        cd ${dstdir}
EOF

        if [ $? -eq 0 ]; then
                echo "${dstdir} is exist"
                return 0
        fi
        lftp -u ${user},${password} -p 21 ftp://${ip} << EOF
        mkdir ${dstdir} -p
EOF
        if [ $? -eq 0 ]; then
                echo "mkdir ${dstdir}"
                return 0
        else
                echo "mkdir ${dstdir} failed!"
                return 1
        fi
}


myftp_to_somewhere() {
        echo "this is myftp_to_somewhere"

        local key=$1
        local oneline=(${dic[$key]})
        local servername=$key
        local srcpath=${oneline[0]}
        local remote_dstdir=${oneline[2]}/$datetime
        local backup_per=${oneline[3]}
        local backup_sto=${oneline[4]}
        local save_time=${oneline[5]}


        local uuid=`uuidgen`
	local _datetime=${datetime_tosql/ /_}
        local filename=`hostname`_${_datetime}_${servername}_conf.tar.gz

        if [ ! -d $srcpath ]; then
                echo "$srcpath is not exist, skip"
                return
        fi


        local ip=`crudini --get ${INI_FILE} ftp ip`
        local remote_user=`crudini --get ${INI_FILE} ftp user`
        local remote_password=`crudini --get ${INI_FILE} ftp password`
        echo "ip is $ip"
        echo "remote_user is ${remote_user}"
        echo "remote_password is ${remote_password}"
        echo "remote_dstdir is ${remote_dstdir}"

        check_and_mkpath_ftp $ip $remote_user $remote_password $remote_dstdir
	if [ $? -ne 0 ]; then
		echo "remote dstdir $remote_dstdir make failed, skip!"
		return
	fi

        local tmpdir="/tmp/$servername"
        check_and_mkpath $tmpdir
        rm -rf $tmpdir/*

        pushd $srcpath
        echo "tar -czvf $tmpdir/$filename $srcpath/*"
        tar -czvf $tmpdir/$filename ./*
        if [ $? -eq 0 -o $? -eq 1 ]; then


		echo "lftp -u ${remote_user},${remote_password} -p 21 ftp://${ip} : mirror -R $tmpdir $remote_dstdir"
		lftp -u ${remote_user},${remote_password} -p 21 ftp://${ip} > /dev/null 2>&1 << EOF
			mirror -R $tmpdir $remote_dstdir
EOF
                if [ $? -eq 0 ]; then
                        ADD_TABLE_SQL="insert into backup.etc_backup values(\"$uuid\", \"$servername\", \"$filename\", \"$srcpath\", \"$dstdir\", \"${remote_dstdir}\", \"${datetime_tosql}\", \"$backup_per\", \"$backup_sto\", \"$save_time\");"
                        echo "ADD_TABLE_SQL is $ADD_TABLE_SQL"
                        mysql -u root -e "${ADD_TABLE_SQL}" -p$password
			if [ $? -ne 0 ]; then
				exit 1
			fi
                else
                        echo "not insert to database, skipped!"
                fi

        fi
        popd

}

get_backup_operation() {
	eval oper=$1
	local type=`crudini --get ${INI_FILE} conf backup_type`
	echo "type is $type"
	case $type in
		local)
			eval $oper='mytar_to_somewhere'
			;;
		scp)
			eval $oper='myscp_to_somewhere'
			get_package expect expect
			;;
		ftp)
			eval $oper='myftp_to_somewhere'
			get_package lftp lftp
			;;
		*)
			echo "in *"
			;;
	esac
}


main() {
	if [ `id -u` -ne 0 ]; then
		echo "please use root privileges"
		exit
	fi

	#read -p "input mysql password: " password
	password=`crudini --get ${INI_FILE} conf mysql_password`

	get_package crudini crudini
	get_backup_operation operation
	#echo "operation is" $operation

	create_mysql
	init_dic
	add_dic_from_ini
	
	for key in ${!dic[*]}; do
		eval $operation $key
	done
}

main
