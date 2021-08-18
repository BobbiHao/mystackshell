#!/bin/bash

INI_FILE=test.ini

read -p "input mysql password: " password

check_and_mkpath() {
	local dir=$1
	if [ -e $dir -a ! -d $dir ]; then
        	panic "$dir is exist but not a dir";
	fi
	[ -d $dir ] || (echo "mkdir $dir";mkdir $dir -p)

}

datetime=`date +%Y-%m-%d`
datetime_tosql=`date "+%Y-%m-%d %H:%M:%S"`

BAK_PREFIX="/root/bak"

check_and_mkpath $BAK_PREFIX


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
		backup_period=`crudini --get ${INI_FILE} $key backup_period`
		backup_volume=`crudini --get ${INI_FILE} $key backup_volume`
		save_time=`crudini --get ${INI_FILE} $key save_time`
		dic[$key]+=" $backup_dst $backup_period $backup_volume $save_time"
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
}

mytar_to_somewhere() {
	local key=$1
	local oneline=(${dic[$key]})
	local servername=$key
	local srcpath=${oneline[0]}
	local dstdir=${oneline[1]}/$datetime
	local backup_per=${oneline[2]}
	local backup_sto=${oneline[3]}
	local save_time=${oneline[4]}

	local uuid=`uuidgen`

	local filename=`hostname`_${datetime}_${servername}_conf.tar.gz

	if [ ! -d $srcpath ]; then
		echo "$srcpath is not exist, skip"
		return
	fi

	check_and_mkpath $dstdir

	pushd $srcpath
	echo "tar -czvf $dstdir/$filename $srcpath/*"
	tar -czvf $dstdir/$filename ./*
	if [ $? -eq 0 -o $? -eq 1 ]; then

		ADD_TABLE_SQL="insert into backup.etc_backup values(\"$uuid\", \"$servername\", \"$filename\", \"$srcpath\", \"$dstdir\", \"${datetime_tosql}\", \"$backup_per\", \"$backup_sto\", \"$save_time\");"	
		echo "ADD_TABLE_SQL is $ADD_TABLE_SQL"
		mysql -u root -e "${ADD_TABLE_SQL}" -p$password

	fi
	popd
}

myscp_to_somewhere() {
	echo "this is myscp_to_somewhere"
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
			;;
		ftp)
			;;
		*)
			echo "in *"
			;;
	esac
}


main() {
	get_backup_operation operation
	echo "operation is" $operation


	create_mysql
	init_dic
	add_dic_from_ini
	
	for key in ${!dic[*]}; do
		eval $operation $key
	done
}

main
