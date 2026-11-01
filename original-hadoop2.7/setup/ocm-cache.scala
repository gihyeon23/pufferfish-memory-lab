// 06b: Flex executor 힙을 컨테이너 limit 이상으로 채워 OCM → puff 유도 (spark-ocm-flex.sh가 spark-shell -i로 실행)
//   executor마다 MB_PER_EXEC개의 1MB 배열을 MEMORY_ONLY로 cache → HOLD_SEC 동안 유지 → 다시 읽기(swap된 페이지 접근)
import org.apache.spark.storage.StorageLevel
val execs = sc.getConf.getInt("spark.executor.instances", 2)
val mbPerExec = sys.env.getOrElse("MB_PER_EXEC", "3000").toInt
val holdSec = sys.env.getOrElse("HOLD_SEC", "60").toInt
val t0 = System.currentTimeMillis
// spark-shell -i는 한 줄씩 해석 → 점(.)으로 시작하는 줄을 새 문장으로 봄. 체인은 한 줄로
val rdd = sc.parallelize(1 to execs * mbPerExec, execs * 10).map(_ => new Array[Byte](1 << 20)).persist(StorageLevel.MEMORY_ONLY)
println(s"[06b] cached ${rdd.count()} MB in ${(System.currentTimeMillis - t0) / 1000}s")
Thread.sleep(holdSec * 1000L)
val t1 = System.currentTimeMillis
println(s"[06b] second pass ${rdd.map(_.length.toLong).sum() / (1 << 20)} MB in ${(System.currentTimeMillis - t1) / 1000}s")
System.exit(0)
