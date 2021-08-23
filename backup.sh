#!/bin/bash

INI_FILE=backup.ini

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
	which $1 &>/dev/null
	if [ $? -ne 0 ]; then
		${APT} install $2 -y
		if [ $? -ne 0 ]; then
        		echo "$2 is install failed!";
			exit 1
		fi
	fi
}


get_value() {
	local section=$1
	local key=$2
	local res=`crudini --get ${INI_FILE} $section $key 2>/dev/null`
	echo $res
}

get_sections() {
	get_value
}

echo_line_flag() {
	echo -ne "\033[34m------------------------"
	echo -ne $1
	echo -e  "------------------------\033[0m"
}
echo_red() {
	local line=$1
	echo -e "\033[41m${line}\033[0m"
}
echo_green() {
	local line=$1
	echo -e "\033[42m${line}\033[0m"
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

#[${NOVA}]=	'$ETC_NOVA               $BAK_NOVA       每周备份一次    52      12'
#[${NEUTRON}]=	'$ETC_NEUTRON            $BAK_NEUTRON    每周备份一次    24      12'
add_dic_from_ini() {
	echo_line_flag "INIT DIC FROM INI"
	for key in `get_sections`; do
		case $key in
			conf | scp | ftp):
				continue;;
		esac
		local backup_type=$(get_value conf backup_type)
		local backup_src=`get_value $key src_path`
		local backup_dst=`get_value $key backup_dstdir`
		local backup_remotedst=`get_value $key remote_dstdir`
		local backup_period=`get_value $key backup_period`
		local backup_volume=`get_value $key backup_volume`
		local save_time=`get_value $key save_time`
		if [ "x"$backup_src = x ]; then
			echo_red "get_value $key src_path is null, skip!"
			continue	
		fi
		if [ "x"$backup_dst = x ] &&  [ $backup_type = "local" ]; then
			echo_red "get_value $key backup_dstdir is null, skip!"
			continue	
		fi
		if [ "x"$backup_remotedst = x ] &&  ([ $backup_type = "scp" ] || [ $backup_type = "ftp" ]); then
			echo_red "get_value $key remote_dstdir is null, skip!"
			continue	
		fi
		dic[$key]+=" $backup_src $backup_dst $backup_remotedst $backup_period $backup_volume $save_time"
		echo "dic[$key] = ${dic[$key]}"
	done
	echo_line_flag "INIT DIC FROM INI END"
}

save_redis() {
	get_value redis &>/dev/null
	if [ $? -ne 0 ]; then
		echo_red "ini has no redis, skip to save it..."
		exit 1
	fi

	local bak_dst=`get_value redis src_path`	
	if [ "x"$bak_dst = "x" ]; then
		exit 1
	fi


    	redis-cli CONFIG GET dir | grep "NOAUTH Authentication required"
	if [ $? -eq 0 ]; then
		local password=`get_value redis server-password`
		if [ "x"$password = "x" ]; then
			exit 1
		fi
		PASS="-a ${password}"
	else
		PASS=
	fi

	#echo "PASS=${PASS}"
	check_and_mkpath $bak_dst
	redis-cli $PASS >/dev/null << EOF
		CONFIG SET dir ${bak_dst}
		SAVE
EOF

	if [ $? -eq 0 ]; then
		echo "redis data save succeed..."
	else
		echo "redis data saved failed!!!"
		exit 1
	fi
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
	mysql -u root -e "${CREATE_TABLE_SQL}" -p$password &>/dev/null
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
		echo_red "in mytar_to_somewhere: $srcpath is not exist, skip"
		return
	fi

	check_and_mkpath $dstdir

	pushd $srcpath
	echo "tar -czvf $dstdir/$filename $srcpath/*" >/dev/null
	echo_green "please wait..."
	tar -czvf $dstdir/$filename ./*
	if [ $? -eq 0 -o $? -eq 1 ]; then

		ADD_TABLE_SQL="insert into backup.etc_backup values(\"$uuid\", \"$servername\", \"$filename\", \"$srcpath\", \"$dstdir\", \"$remote_dstdir\", \"${datetime_tosql}\", \"$backup_per\", \"$backup_sto\", \"$save_time\");"	
		echo "$ADD_TABLE_SQL"
		mysql -u root -e "${ADD_TABLE_SQL}" -p$password &>/dev/null
		if [ $? -ne 0 ]; then
			exit 1
		fi

	fi
	popd >/dev/null
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
		echo_red "$srcpath is not exist, skip"
		return
	fi


	local ip=`get_value scp ip`
	local remote_user=`get_value scp user`
	local remote_password=`get_value scp password`
	echo -n "ip is $ip,"
	echo -n " remote_user is ${remote_user},"
	echo -n " remote_password is ${remote_password},"
	echo    " remote_dstdir is ${remote_dstdir}"

	check_and_mkpath_ssh $remote_dstdir $remote_user $ip $remote_password

	local tmpdir="/tmp/$servername"
	check_and_mkpath $tmpdir
	rm -rf $tmpdir/*

	pushd $srcpath
	echo "tar -czvf $tmpdir/$filename $srcpath/*" >/dev/null
	echo_green "please wait..."
	tar -czvf $tmpdir/$filename ./*
	if [ $? -eq 0 -o $? -eq 1 ]; then

		echo "scp $tmpdir/$filename $remote_user $ip $remote_password $remote_dstdir"
		scp_expect $tmpdir/$filename $remote_user $ip $remote_password $remote_dstdir 
		if [ $? -eq 0 ]; then
			ADD_TABLE_SQL="insert into backup.etc_backup values(\"$uuid\", \"$servername\", \"$filename\", \"$srcpath\", \"$dstdir\", \"${remote_dstdir}\", \"${datetime_tosql}\", \"$backup_per\", \"$backup_sto\", \"$save_time\");"	
			echo "$ADD_TABLE_SQL"
			mysql -u root -e "${ADD_TABLE_SQL}" -p$password &>/dev/null
			if [ $? -ne 0 ]; then
				exit 1
			fi
		else
			echo_red "not insert to database, skipped!"
		fi

	fi
	popd >/dev/null

}

#check_and_mkpath_ftp 192.168.40.130 bobbi qwer1234 /shell
check_and_mkpath_ftp() {
        local ip=$1
        local user=$2
        local password=$3
        local dstdir=$4

        lftp -u ${user},${password} -p 21 ftp://${ip} &>/dev/null << EOF
        cd ${dstdir}
EOF

        if [ $? -eq 0 ]; then
                #echo "${dstdir} is exist"
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
                echo_red "$srcpath is not exist, skip"
                return
        fi


        local ip=`get_value ftp ip`
        local remote_user=`get_value ftp user`
        local remote_password=`get_value ftp password`
        echo -n "ip is $ip,"
        echo -n " remote_user is ${remote_user},"
        echo -n " remote_password is ${remote_password},"
        echo    " remote_dstdir is ${remote_dstdir}"

        check_and_mkpath_ftp $ip $remote_user $remote_password $remote_dstdir
	if [ $? -ne 0 ]; then
		echo_red "remote dstdir $remote_dstdir make failed, skip!"
		return
	fi

        local tmpdir="/tmp/$servername"
        check_and_mkpath $tmpdir
        rm -rf $tmpdir/*

        pushd $srcpath >/dev/null
        echo "tar -czvf $tmpdir/$filename $srcpath/*"
	echo_green "please wait..."
        tar -czvf $tmpdir/$filename ./* >/dev/null
        if [ $? -eq 0 -o $? -eq 1 ]; then


		echo "lftp -u ${remote_user},${remote_password} -p 21 ftp://${ip} : mirror -R $tmpdir $remote_dstdir"
		lftp -u ${remote_user},${remote_password} -p 21 ftp://${ip} > /dev/null 2>&1 << EOF
			mirror -R $tmpdir $remote_dstdir
EOF
                if [ $? -eq 0 ]; then
                        ADD_TABLE_SQL="insert into backup.etc_backup values(\"$uuid\", \"$servername\", \"$filename\", \"$srcpath\", \"$dstdir\", \"${remote_dstdir}\", \"${datetime_tosql}\", \"$backup_per\", \"$backup_sto\", \"$save_time\");"
                        echo "$ADD_TABLE_SQL"
                        mysql -u root -e "${ADD_TABLE_SQL}" -p$password &>/dev/null
			if [ $? -ne 0 ]; then
				exit 1
			fi
                else
                        echo_red "not insert to database, skipped!"
                fi

        fi
        popd >/dev/null

}

get_backup_operation() {
	eval oper=$1
	local type=`get_value conf backup_type`
	echo "backup type is $type"
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
			echo "please ensure the backup type!"
			exit 1
			;;
	esac
}


main() {
	if [ `id -u` -ne 0 ]; then
		echo "please use root privileges"
		exit
	fi

	get_package crudini crudini
	#read -p "input mysql password: " password
	password=`get_value conf mysql_password`


	save_redis

	get_backup_operation operation
	#echo "operation is" $operation

	create_mysql
	add_dic_from_ini

	for key in ${!dic[*]}; do
		eval $operation $key
	done
}

main
