#!/usr/bin/env bash

config_file=/etc/birdnet/birdnet.conf
if [ -f ${config_file} ];then
    source ${config_file}
else
    echo "Unable to find a configuration file. Please make sure that $config_file exists."
    exit 1
fi

export PYTHON_VIRTUAL_ENV="$HOME/BirdNET-Pi/birdnet/bin/python3"

# Check LUISTERVINK_ENABLE_TASK_PROCESSOR and run Python script if true
if [[ "${LUISTERVINK_ENABLE_TASK_PROCESSOR,,}" == "true" ]]; then
    $PYTHON_VIRTUAL_ENV /usr/local/bin/luistervink_tasks.py
else
    echo "LUISTERVINK_ENABLE_TASK_PROCESSOR is not enabled, skipping task processing."
fi
