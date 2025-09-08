import logging
from pyspark.sql import SparkSession
from pyspark.sql.functions import col, to_timestamp, split
from pyspark.sql.types import IntegerType, DoubleType, StringType

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("TransactionDataCleaning")

logger.info("Starting Spark session")
spark = SparkSession.builder \
    .appName("ReadHDFSFile") \
    .config("spark.executor.memory", "2g") \
    .config("spark.driver.memory", "1g") \
    .config("spark.executor.memoryOverhead", "512m") \
    .config("spark.sql.adaptive.enabled", "true") \
    .config("spark.sql.adaptive.coalescePartitions.enabled", "true") \
    .getOrCreate()

logger.info("Reading data from HDFS")
df = spark.read.text("hdfs:///user/ubuntu/data/*.txt")

columns = ["transaction_id", "tx_datetime", "customer_id", "terminal_id", "tx_amount", "tx_time_seconds", "tx_time_days", "tx_fraud", "tx_fraud_scenario"]

logger.info("Filtering header rows")
df = df.filter(~col("value").startswith("#"))

logger.info("Splitting and selecting columns")
df = df.withColumn("split_values", split(col("value"), ","))
df = df.select(
    col("split_values").getItem(0).alias("transaction_id"),
    col("split_values").getItem(1).alias("tx_datetime"),
    col("split_values").getItem(2).alias("customer_id"),
    col("split_values").getItem(3).alias("terminal_id"),
    col("split_values").getItem(4).alias("tx_amount"),
    col("split_values").getItem(5).alias("tx_time_seconds"),
    col("split_values").getItem(6).alias("tx_time_days"),
    col("split_values").getItem(7).alias("tx_fraud"),
    col("split_values").getItem(8).alias("tx_fraud_scenario")
)

logger.info("Casting columns to correct data types")
df = df.select(
    col("transaction_id").cast(IntegerType()),
    col("tx_datetime").cast(StringType()),
    col("customer_id").cast(IntegerType()),
    col("terminal_id").cast(IntegerType()),
    col("tx_amount").cast(DoubleType()),
    col("tx_time_seconds").cast(IntegerType()),
    col("tx_time_days").cast(IntegerType()),
    col("tx_fraud").cast(IntegerType()),
    col("tx_fraud_scenario").cast(IntegerType())
)

logger.info("Dropping rows with nulls in mandatory fields")
mandatory_fields = ["transaction_id", "tx_datetime", "customer_id", "tx_amount"]
df_clean = df.dropna(subset=mandatory_fields)

logger.info("Converting tx_datetime to timestamp and filtering invalid rows")
df_clean = df_clean.withColumn("tx_timestamp", to_timestamp(col("tx_datetime"), "yyyy-MM-dd HH:mm:ss"))
df_clean = df_clean.filter(col("tx_timestamp").isNotNull())

logger.info("Filtering rows with valid tx_amount > 0")
df_clean = df_clean.filter(col("tx_amount") > 0)

logger.info("Filtering rows with tx_fraud only 0 or 1")
df_clean = df_clean.filter(col("tx_fraud").isin(0, 1))

logger.info("Dropping duplicate transaction_id records")
df_clean = df_clean.dropDuplicates(["transaction_id"])

output_path = "cleaned.parquet"
logger.info(f"Saving cleaned data to Parquet file at {output_path}")
df_clean.write.mode("overwrite").parquet(output_path)

logger.info("Stopping Spark session")
spark.stop()
