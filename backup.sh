#!/usr/bin/bash

DEPENCIES_DIR=./depencies

isInstalled() {
	package=$1
	pip3 show $package >/dev/null 2>&1
	if [ $? -eq 0 ]; then
		return 0
	fi
	return 1
}

isExists() {
	path=$1
	ls $path >/dev/null 2>&1
	if [ $? -eq 0 ]; then
		return 0
	fi
	return 1
}

fd_install_depencies() {
	isInstalled "APScheduler"
	in1=$?
	isInstalled "crudini"
	in2=$?
	isInstalled "pymysql"
	in3=$?

	echo "in1 is $in1, in2 is $in2, in3 is $in3"
	if [[ $in1 -ne 0 ]] || [[ $in2 -ne 0 ]] || [[ $in3 -ne 0 ]]; then
		echo "will install $DEPENCIES_DIR/*"
		pip3 install $DEPENCIES_DIR/*
	fi

	isExists "/usr/bin/crudini"
	e1=$?
	isExists "/usr/local/bin/crudini"
	e2=$?
	if [[ $e1 -ne 0 ]] && [[ $e2 -eq 0 ]]; then
		ln /usr/local/bin/crudini -s /usr/bin/crudini
	fi
}

main() {
	if [ `id -u` -ne 0 ]; then
                echo "please use root privileges"
                exit
        fi
	fd_install_depencies
	python3 ./backup.py	
}

main
