# task 이미지 — sequenceiq/hadoop-docker와 같은 역할 (Java + Hadoop + 설정)
# DCE는 호스트의 Hadoop/JDK를 마운트하지 않으므로 이미지 안에 같은 경로로 둔다
FROM local/ubuntu:16.04

RUN apt-get update \
 && apt-get install -y --no-install-recommends openjdk-8-jdk-headless \
 && rm -rf /var/lib/apt/lists/*

# 공식 2.7.3 + 원 저자 YARN jar 13개 교체본 (build-image.sh가 컨텍스트에 복사)
ADD hadoop-2.7.3-pufferfish.tar.gz /opt/
COPY conf/*.xml /opt/hadoop-2.7.3/etc/hadoop/

ENV JAVA_HOME=/usr/lib/jvm/java-8-openjdk-arm64 \
    HADOOP_PREFIX=/opt/hadoop-2.7.3 \
    HADOOP_COMMON_HOME=/opt/hadoop-2.7.3 \
    HADOOP_HDFS_HOME=/opt/hadoop-2.7.3 \
    HADOOP_MAPRED_HOME=/opt/hadoop-2.7.3 \
    HADOOP_YARN_HOME=/opt/hadoop-2.7.3 \
    HADOOP_CONF_DIR=/opt/hadoop-2.7.3/etc/hadoop \
    PATH=/opt/hadoop-2.7.3/bin:/usr/lib/jvm/java-8-openjdk-arm64/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
