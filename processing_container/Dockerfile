FROM amazonlinux


# Install dependencies
RUN yum update -y && \
 yum install -y git && \
 yum install -y awscli && \
 curl -O https://bootstrap.pypa.io/get-pip.py && \
 python3 get-pip.py && \
 pip3 install -r requirements.txt

# Install code
RUN git clone https://github.com/drumadrian/s3-to-elasticsearch-access-logs.git


#  Write message to identify the container purpose
RUN echo 's3-to-elasticsearch!' > /root/CONTAINER_README.md


# Configure application
RUN echo '. /etc/apache2/envvars' > /root/run_apache.sh && \
 echo 'mkdir -p /var/run/apache2' >> /root/run_apache.sh && \
 echo 'mkdir -p /var/lock/apache2' >> /root/run_apache.sh && \
 echo '/usr/sbin/apache2 -D FOREGROUND' >> /root/run_apache.sh && \
 chmod 755 /root/run_apache.sh


ENTRYPOINT python3 sqs_to_elasticsearch_service/sqs_to_elasticsearch_service_EC2.py

