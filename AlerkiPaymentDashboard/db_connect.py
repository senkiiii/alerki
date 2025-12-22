import mysql.connector

conn = mysql.connector.connect(
    host="127.0.0.1",      # Not "localhost"
    user="root",
    password="1234",
    database="pebi",
    port=3306
)
