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
	in1=$(isInstalled "APScheduler")
	in2=$(isInstalled "crudini")
	in3=$(isInstalled "pymysql")

	if [[ $in1 -ne 0 ]] || [[ $in2 -ne 0 ]] || [[ $in3 -ne 0 ]]; then
		pip3 install $DEPENCIES_DIR/*
	fi

	e1=$(isExists "/usr/bin/crudini")
	e2=$(isExists "/usr/local/bin/crudini")
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
