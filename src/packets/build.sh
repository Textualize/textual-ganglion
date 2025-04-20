#!/bin/bash
python -m venv $1/.packets
$1/.packets/bin/pip install -r $1/requirements.txt
$1/.packets/bin/python $1/build.py $1 $2
$1/.packets/bin/python $2
$1/.packets/bin/python -m black $2
