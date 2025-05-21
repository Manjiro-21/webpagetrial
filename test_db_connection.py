import mysql.connector
from werkzeug.security import generate_password_hash, check_password_hash

try:
    db = mysql.connector.connect(
        host="localhost",
        user="root",
        password="Appa@@@1980@@@",
    )
    cursor = db.cursor()
    cursor.execute("SHOW DATABASES;")
    print("Available databases:")
    for x in cursor:
        print(" -", x[0])
    db.close()
except mysql.connector.Error as err:
    print("❌ Error connecting to MySQL:", err)

from werkzeug.security import generate_password_hash
print(generate_password_hash("mainofficer123"))