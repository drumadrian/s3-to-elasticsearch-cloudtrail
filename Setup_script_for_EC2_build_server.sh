# Setup script for EC2 build server



################################################################################################################
# REFERENCES 
################################################################################################################
# https://www.hostinger.com/tutorials/how-to-install-and-use-linux-screen/
# https://docs.aws.amazon.com/elasticbeanstalk/latest/dg/eb-cli3-install-linux.html
# https://docs.aws.amazon.com/sdk-for-javascript/v2/developer-guide/setting-up-node-on-ec2-instance.html
# https://stackoverflow.com/questions/2915471/install-a-python-package-into-a-different-directory-using-pip

################################################################################################################
#   Update the Operating System packages and install tools
################################################################################################################
sudo yum update -y

sudo yum install -y git

curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.34.0/install.sh | bash

. ~/.nvm/nvm.sh

nvm install node

node -e "console.log('Running Node.js ' + process.version)"

npm install -g aws-cdk

sudo yum install -y screen

sudo yum install -y python37

curl -O https://bootstrap.pypa.io/get-pip.py

python3 get-pip.py

pip3 install -U pip

aws configure set region us-west-2

git clone https://github.com/drumadrian/s3-to-elasticsearch-access-logs.git

cd s3-to-elasticsearch-access-logs/cdk

pip3 install -r requirements.txt 

cd sqs_to_elasticsearch_service/

pip3 install -r requirements.txt --target=.

cd ../sqs_to_elastic_cloud/

pip3 install -r requirements.txt --target=.

cd ..

cdk bootstrap

cdk deploy

