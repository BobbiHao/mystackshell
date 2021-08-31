#!/bin/bash

INI_FILE=backup.ini

datetime=`date +%Y-%m-%d`
datetime_tosql=`date "+%Y-%m-%d %H:%M:%S"`

REDIS_TMP=/tmp/redis-save
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
	if [ -e $dir ] && [ ! -d $dir ]; then
        	echo "$dir is exist but not a dir";
		exit 1
	fi
	[ -d $dir ] || (echo "mkdir $dir";mkdir $dir -p)

}

declare -A dic

#[${NOVA}]=	'$ETC_NOVA               $BAK_NOVA       每周备份一次    52      12'
#[${NEUTRON}]=	'$ETC_NEUTRON            $BAK_NEUTRON    每周备份一次    24      12'
add_dic_from_ini() {
	local src_path unit data_type backup_dst backup_remotedst backup_period backup_volume save_time

	local backup_type=`get_value conf backup_type`

	echo_line_flag "INIT DIC FROM INI"
	for key in `get_sections`; do
		src_path=
		unit=
		data_type=
		backup_dst= 
		backup_remotedst= 
		backup_period=
		backup_volume=
		save_time=

		case $key in
			conf | scp | ftp):
				continue;;
		esac
		#local backup_type=$(get_value conf backup_type)
		if [[ $key = /* ]]; then
			src_path=$key
		else
			if [[ "x"$key = "xredis" ]]; then
				src_path=$REDIS_TMP
			else
				echo_red "$key is not begin with /, and it is no redis, exit!"
				exit 1
			fi
		fi
		unit=`get_value $key unit`
		data_type=`get_value $key data_type`
		if [[ "x"${backup_type} = xlocal ]]; then
			backup_dst=`get_value $key backup_dstdir`
		else
			backup_dst="-"
		fi
		if [[ "x"${backup_type} = xscp ]] || [[ "x"${backup_type} = xftp ]]; then
			backup_remotedst=`get_value $key remote_dstdir`
		else
			backup_remotedst="-"
		fi
		backup_period=`get_value $key backup_period`
		backup_volume=`get_value $key backup_volume`
		save_time=`get_value $key save_time`

		if [[ "x"$backup_dst = x ]] &&  [[ "x"$backup_type = "xlocal" ]]; then
			echo_red "get_value $key backup_dstdir is null, skip!"
			continue	
		fi
		if [[ "x"$backup_remotedst = x ]] &&  ([[ "x"$backup_type = "xscp" ]] || [[ "x"$backup_type = "xftp" ]]); then
			echo_red "get_value $key remote_dstdir is null, skip!"
			continue	
		fi
		dic[${src_path}]+="$unit $data_type $backup_dst $backup_remotedst $backup_period $backup_volume $save_time"
		echo "dic[$src_path] = ${dic[$src_path]}"
	done
	echo_line_flag "INIT DIC FROM INI END"
}

parse_dic_oneline() {
	local key=$1
	#local srcpath=$key
	local oneline=(${dic[$key]})
	local _servername=$2
	local _data_type=$3
	local _dstdir=$4
	local _remote_dstdir=$5
	local _backup_per=$6
	local _backup_sto=$7
	local _save_time=$8

	eval $_servername="${oneline[0]}"
	eval $_data_type="${oneline[1]}"
	if [[ "x"${oneline[2]} != x ]] && [[ "x"${oneline[2]} != "x-" ]]; then
		eval $_dstdir="${oneline[2]}/$datetime"
	fi

	if [[ "x"${oneline[3]} != x ]] && [[ "x"${oneline[3]} != "x-" ]]; then
		eval $_remote_dstdir="${oneline[3]}/$datetime"
	fi
	eval $_backup_per="${oneline[4]}"
	eval $_backup_sto="${oneline[5]}"
	eval $_save_time="${oneline[6]}"
}

save_redis() {
	get_value redis &>/dev/null
	if [ $? -ne 0 ]; then
		echo_red "ini has no redis, skip to save it..."
		return 1
	fi

	check_and_mkpath $REDIS_TMP
	rm -rf $REDIS_TMP/*


    	redis-cli CONFIG GET dir >/dev/null
	if [ $? -ne 0 ]; then
		echo_red "exit from save_redis"
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
	redis-cli $PASS >/dev/null << EOF
		CONFIG SET dir $REDIS_TMP
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

splice_tarfilename() {
	local servername=$1
	local srcpath=$2
	local data_type=$3

	local _datetime=${datetime_tosql/ /_}
	local srcpath_changed=${srcpath//\//_}


	#filename=`hostname`_${_datetime}_${servername}_${srcpath_changed}_${data_type}.tar.gz
	local filename=`hostname`_${_datetime}_${servername}
	while [[ "x"${filename: -1} = "x_" ]];
	do
		filename=${filename%?}
	done

	filename+=${srcpath_changed}
	while [[ "x"${filename: -1} = "x_" ]];
	do
		filename=${filename%?}
	done
	
	filename+=_${data_type}.tar.gz
	echo $filename
}

mytar_to_somewhere() {
	local key=$1
	local srcpath=$key

	local servername data_type dstdir remote_dstdir backup_per backup_sto save_time
	parse_dic_oneline $key servername data_type dstdir remote_dstdir backup_per backup_sto save_time

	echo_green "servernam is $servername, data_type is $data_type, dstdir is $dstdir, remote_dstdir is $remote_dstdir, backup_per is $backup_per"

	local uuid=`uuidgen`
	local filename=$(splice_tarfilename $servername $srcpath $data_type)

	if [ ! -d $srcpath ]; then
		echo_red "in mytar_to_somewhere: $srcpath is not exist, skip"
		return
	fi

	check_and_mkpath $dstdir

	pushd $srcpath >/dev/null
	echo "tar -czvf $dstdir/$filename $srcpath/*" >/dev/null
	echo_green "please wait..."
	tar -czvf $dstdir/$filename ./*
	if [ $? -eq 0 -o $? -eq 1 ]; then

		if [[ "x"$srcpath = x$REDIS_TMP ]]; then
			srcpath=redis
		fi
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


		#dic[$src_path]+=" $unit $data_type $backup_dst $backup_remotedst $backup_period $backup_volume $save_time"
myscp_to_somewhere() {
	local key=$1
	local srcpath=$key

	local servername data_type dstdir remote_dstdir backup_per backup_sto save_time
	parse_dic_oneline $key servername data_type dstdir remote_dstdir backup_per backup_sto save_time

	echo_green "servernam is $servername, data_type is $data_type, dstdir is $dstdir, remote_dstdir is $remote_dstdir, backup_per is $backup_per"

	local uuid=`uuidgen`
	local filename=$(splice_tarfilename $servername $srcpath $data_type)

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
	if [ $? -ne 0 ]; then
		exit 1
	fi

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
			if [[ "x"$srcpath = x$REDIS_TMP ]]; then
				srcpath=redis
			fi
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
	local srcpath=$key

	local servername data_type dstdir remote_dstdir backup_per backup_sto save_time
	parse_dic_oneline $key servername data_type dstdir remote_dstdir backup_per backup_sto save_time

	echo_green "servernam is $servername, data_type is $data_type, dstdir is $dstdir, remote_dstdir is $remote_dstdir, backup_per is $backup_per"

	local uuid=`uuidgen`
	local filename=$(splice_tarfilename $servername $srcpath $data_type)

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
			if [[ "x"$srcpath = x$REDIS_TMP ]]; then
				srcpath=redis
			fi
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
	local backup_type=`get_value conf backup_type`
	if [[ "x"${backup_type} != xlocal ]] && [[ "x"${backup_type} != xscp ]] && [[ "x"${backup_type} != xftp ]]; then
		echo_red "please ensure your backup_type in conf"
		exit 1
	fi

	echo "backup type is ${backup_type}"
	case ${backup_type} in
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


Backup() {
	save_redis

	get_backup_operation operation
	#echo "operation is" $operation

	create_mysql
	add_dic_from_ini

	for key in ${!dic[*]}; do
		eval $operation $key
	done
}

Restore() {
	echo "will restore"
	if [ $# -eq 0 ]; then
		echo "no args"
	else
		local onepath=$1
		echo "onepath is $onepath"
	fi




}

main() {
	if [ `id -u` -ne 0 ]; then
		echo "please use root privileges"
		exit
	fi

	get_package crudini crudini
	#read -p "input mysql password: " password
	password=`get_value conf mysql_password`


	local backup_or_restore=`get_value conf backup_or_restore`
	if [[ "x"${backup_or_restore} = "xbackup" ]]; then
		Backup
	elif [[ "x"${backup_or_restore} = "xrestore" ]]; then
		Restore	$@
	else
		echo_red "It is neither a backup nor a restore. exit!"
		exit 1
	fi

	echo_green "succeed, good bye"
}

main $@
