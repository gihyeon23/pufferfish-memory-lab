package lab.pufferfish;

import java.lang.management.ManagementFactory;
import java.lang.management.MemoryMXBean;
import java.lang.management.MemoryUsage;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.List;

/**
 * Pufferfish 실험용 워크로드.
 *
 * 일정 간격마다 고정 크기의 메모리 청크를 할당하고 계속 참조하여
 * GC가 회수하지 못하게 만든다. 컨테이너 메모리 사용량 증가, CPU 제한,
 * puff()/reclaim() 동작 실험의 기반이 되는 프로그램이다.
 */
public final class MemoryGrowthWorkload {

    private static final DateTimeFormatter TIMESTAMP_FORMAT =
            DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss");

    private static final long BYTES_PER_MB = 1024L * 1024L;

    public static void main(String[] args) {
        Config config;
        try {
            config = Config.fromEnvironment();
        } catch (IllegalArgumentException e) {
            System.err.println("설정 오류: " + e.getMessage());
            System.exit(1);
            return;
        }

        System.out.printf(
                "설정: CHUNK_SIZE_MB=%d, INTERVAL_SECONDS=%d, MAX_ALLOCATION_MB=%d%n",
                config.chunkSizeMb, config.intervalSeconds, config.maxAllocationMb);

        MemoryMXBean memoryBean = ManagementFactory.getMemoryMXBean();
        List<byte[]> retainedChunks = new ArrayList<>();
        long chunkSizeBytes = config.chunkSizeMb * BYTES_PER_MB;
        long maxAllocationBytes = config.maxAllocationMb * BYTES_PER_MB;
        long totalAllocatedBytes = 0;
        int allocationCount = 0;
        boolean maxReached = false;

        while (true) {
            if (!maxReached) {
                if (totalAllocatedBytes + chunkSizeBytes > maxAllocationBytes) {
                    maxReached = true;
                    System.out.printf(
                            "[%s] 최대 누적 할당량(%dMiB)에 도달했습니다. 메모리를 유지한 채 대기합니다.%n",
                            now(), config.maxAllocationMb);
                } else {
                    try {
                        byte[] chunk = new byte[(int) chunkSizeBytes];
                        fill(chunk);
                        retainedChunks.add(chunk);
                        totalAllocatedBytes += chunkSizeBytes;
                        allocationCount++;

                        logAllocation(memoryBean, allocationCount, config.chunkSizeMb,
                                totalAllocatedBytes);
                    } catch (OutOfMemoryError e) {
                        System.err.printf(
                                "[%s] OutOfMemoryError 발생. 누적 할당량: %d MiB (%d회 할당)%n",
                                now(), totalAllocatedBytes / BYTES_PER_MB, allocationCount);
                        return;
                    }
                }
            }

            try {
                Thread.sleep(config.intervalSeconds * 1000L);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                System.out.printf("[%s] 인터럽트를 받아 종료합니다. 누적 할당량: %d MiB%n",
                        now(), totalAllocatedBytes / BYTES_PER_MB);
                return;
            }
        }
    }

    private static void fill(byte[] chunk) {
        // 실제 물리 메모리 사용량이 증가하도록 페이지 전체에 값을 기록한다.
        java.util.Arrays.fill(chunk, (byte) 1);
    }

    private static void logAllocation(MemoryMXBean memoryBean, int allocationCount,
            long chunkSizeMb, long totalAllocatedBytes) {
        MemoryUsage heapUsage = memoryBean.getHeapMemoryUsage();
        System.out.printf(
                "[%s] 할당 #%d | +%dMiB | 누적 %dMiB | JVM used=%dMiB committed=%dMiB max=%dMiB%n",
                now(),
                allocationCount,
                chunkSizeMb,
                totalAllocatedBytes / BYTES_PER_MB,
                heapUsage.getUsed() / BYTES_PER_MB,
                heapUsage.getCommitted() / BYTES_PER_MB,
                heapUsage.getMax() / BYTES_PER_MB);
    }

    private static String now() {
        return LocalDateTime.now().format(TIMESTAMP_FORMAT);
    }

    private static final class Config {
        final long chunkSizeMb;
        final long intervalSeconds;
        final long maxAllocationMb;

        private Config(long chunkSizeMb, long intervalSeconds, long maxAllocationMb) {
            this.chunkSizeMb = chunkSizeMb;
            this.intervalSeconds = intervalSeconds;
            this.maxAllocationMb = maxAllocationMb;
        }

        static Config fromEnvironment() {
            long chunkSizeMb = readPositiveLong("CHUNK_SIZE_MB", 32);
            long intervalSeconds = readPositiveLong("INTERVAL_SECONDS", 5);
            long maxAllocationMb = readPositiveLong("MAX_ALLOCATION_MB", 512);

            if (chunkSizeMb > maxAllocationMb) {
                throw new IllegalArgumentException(
                        "CHUNK_SIZE_MB(" + chunkSizeMb + ")는 MAX_ALLOCATION_MB(" + maxAllocationMb
                                + ")보다 클 수 없습니다.");
            }
            if (chunkSizeMb > 2048) {
                throw new IllegalArgumentException(
                        "CHUNK_SIZE_MB(" + chunkSizeMb + ")가 너무 큽니다. byte[] 배열 한계(약 2048MiB) 이하로 설정하세요.");
            }

            return new Config(chunkSizeMb, intervalSeconds, maxAllocationMb);
        }

        private static long readPositiveLong(String envName, long defaultValue) {
            String raw = System.getenv(envName);
            if (raw == null || raw.isBlank()) {
                return defaultValue;
            }

            long value;
            try {
                value = Long.parseLong(raw.trim());
            } catch (NumberFormatException e) {
                throw new IllegalArgumentException(
                        envName + " 값이 올바른 정수가 아닙니다: \"" + raw + "\"");
            }

            if (value <= 0) {
                throw new IllegalArgumentException(
                        envName + " 값은 0보다 커야 합니다: " + value);
            }

            return value;
        }
    }
}
