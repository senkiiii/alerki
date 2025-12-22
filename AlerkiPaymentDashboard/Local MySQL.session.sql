import mysql.connector

# Establish connection
db = mysql.connector.connect(
    host="localhost",
    user="root",
    password="1234",
    database="pebi"
)

print("Connected to MySQL successfully!")
