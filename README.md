### Raw run
  
prepare config  
`cp config.ini.sample config.ini`  
open/fill configuration file  
then  
`python -m pip install -r requirements.txt`
`python -m src`


### Docker run

`mkdir data`  
prepare config  
`cp config.ini.sample data/config.ini`  
open/fill configuration file  
then  
`docker-compose up -d --build`
