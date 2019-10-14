from airflow import DAG
from airflow.operators.bash_operator import BashOperator
from airflow.operators.email_operator import EmailOperator
from airflow.operators.python_operator import PythonOperator
from airflow.operators.http_operator import SimpleHttpOperator
from airflow.operators.sensors import HttpSensor, SqlSensor
from airflow.utils.email import send_email
from datetime import datetime, timedelta
import sys
import psycopg2
import subprocess

defaultArgs = {
	"owner": "Nicholas",
	"retries": 1,
	"retry_delay": timedelta(minutes = 5),
	"start_date": datetime.now(),
	"depends_on_past": False,
	"email": ["nickjpena5@gmail.com"],
	"email_on_failure": True
}


'''
 gather lines from the corresponding file
	filename: string of the name of the file
	return: a list of lines from the file
'''
def readFile(filename):
	try:
		file = open(filename, "r")
	except IOError:
		print("Unable to open file %s" % filename)
		return

	lines = []
	for line in file.readlines():
		lines.append(''.join(line.split()))

	file.close()
	return lines

'''
	once there are requests to fill, remove a request and submit
	the appropriate spark jobs to fulfill it
'''
def schedule():
	databaseCredentials = readFile("/home/ubuntu/InsightProject/database.txt")
	host = databaseCredentials[1]
	database = databaseCredentials[2]
	password = databaseCredentials[3]

	connection = psycopg2.connect(
		host = host, 
		database = database, 
		user = "postgres",
		password = password
	)

	cursor = connection.cursor()
	query = """
		SELECT * FROM requests LIMIT 1;
	"""

	cursor.execute(query)
	results = cursor.fetchall()

	word = results[0][0]
	email = results[0][1]

	query = """
		SELECT COUNT(*) FROM frequenciesthree WHERE word = '{}';
		""".format(word.lower())

	cursor.execute(query)
	results = cursor.fetchall()[0][0]

	if results != 0:
		return 

	query = """
		DELETE FROM requests WHERE word = '{}';
		""".format(word)

	cursor.execute(query)
	connection.commit()

	template = '''
			spark-submit
			--master spark://ec2-3-230-62-227.compute-1.amazonaws.com:7077
			--conf spark.driver.maxResultSize=6g
			--executor-memory 4g
			--driver-memory 6g
			--executor-cores 6
			--jars /home/ubuntu/postgresql-42.2.8.jar
			/home/ubuntu/InsightProject/spark/ingestion.py '''

	months = [
		"January", "February", "March", "April", "May", "June",
		"July", "August", "September", "October", "November", "December"
	]

	for i in range(len(months)):
		bashCommand = template + str(i) + " " + word
		process = subprocess.check_call(bashCommand.split())

		output, error = process.communicate()

	cursor.close()
	connection.close()

	send_email(
			to = email,
			subject = "Processing Job Complete",
			html_content = """Your word '{}' has finished processing!
 		 	 Go query it here:
 		 	 http://lensoftruth.me
 		 	 """.format(word),
		)


dag_id = "monthly_processing"
dag = DAG(dag_id = dag_id,
	 	default_args = defaultArgs,
	 	schedule_interval = timedelta(hours = 7))

sql_sensor = SqlSensor(
		task_id = "check_for_requests",
		conn_id = "insight",
		sql = "SELECT * FROM requests;",
		poke_interval = 30,
		dag = dag
	)

python_task = PythonOperator(
		task_id = "python_task",
		python_callable = schedule,
		dag = dag
	)

python_task << sql_sensor