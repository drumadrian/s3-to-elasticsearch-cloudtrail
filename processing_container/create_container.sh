# build script for creating event processing container from Dockerfile and uploading to AWS ECR

#!/bin/sh
echo Building event processing container s3-to-elasticsearch:build

docker build -t s3-to-elasticsearch:latest .

