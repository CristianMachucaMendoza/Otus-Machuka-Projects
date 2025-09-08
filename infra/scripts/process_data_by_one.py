import logging
import os
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

# Path to HDFS folder with input files
input_path = "hdfs:///user/ubuntu/data/*.txt"

# List all individual files
logger.info("Listing input files")
files = spark.sparkContext._jvm.org.apache.hadoop.fs.FileSystem \
    .get(spark._jsc.hadoopConfiguration()) \
    .globStatus(spark._jvm.org.apache.hadoop.fs.Path(input_path))

# Convert to Python list of file paths
file_list = [f.getPath().toString() for f in files]

logger.info(f"Found {len(file_list)} files to process")

# Process each file one by one
for file in file_list:
    base_name = os.path.basename(file).replace(".txt", "")
    output_path = f"hdfs:///user/ubuntu/cleaned/{base_name}.parquet"

    logger.info(f"Processing file {file}")

    df = spark.read.text(file)

    # Filter header rows
    df = df.filter(~col("value").startswith("#"))

    # Split and select columns
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

    # Cast data types
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

    # Clean data
    mandatory_fields = ["transaction_id", "tx_datetime", "customer_id", "tx_amount"]
    df_clean = df.dropna(subset=mandatory_fields)

    df_clean = df_clean.withColumn("tx_timestamp", to_timestamp(col("tx_datetime"), "yyyy-MM-dd HH:mm:ss"))
    df_clean = df_clean.filter(col("tx_timestamp").isNotNull())
    df_clean = df_clean.filter(col("tx_amount") > 0)
    df_clean = df_clean.filter(col("tx_fraud").isin(0, 1))
    df_clean = df_clean.dropDuplicates(["transaction_id"])

    logger.info(f"Saving cleaned data to {output_path}")
    df_clean.write.mode("overwrite").parquet(output_path)

logger.info("All files processed. Stopping Spark session.")
spark.stop()
