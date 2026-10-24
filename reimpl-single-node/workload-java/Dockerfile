FROM eclipse-temurin:21-jdk AS build

WORKDIR /build
COPY src/main/java/lab/pufferfish/MemoryGrowthWorkload.java src/main/java/lab/pufferfish/MemoryGrowthWorkload.java
RUN javac -d out src/main/java/lab/pufferfish/MemoryGrowthWorkload.java

FROM eclipse-temurin:21-jre

WORKDIR /app
COPY --from=build /build/out /app/out

ENV CHUNK_SIZE_MB=32
ENV INTERVAL_SECONDS=5
ENV MAX_ALLOCATION_MB=512
ENV JAVA_OPTS=""

ENTRYPOINT ["sh", "-c", "exec java $JAVA_OPTS -cp /app/out lab.pufferfish.MemoryGrowthWorkload"]
