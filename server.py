#!/usr/local/bin/python3

from flask import Flask, render_template, request, jsonify
from paramiko.auth_handler import AuthenticationException, SSHException
from paramiko import SSHClient, AutoAddPolicy, RSAKey
import pandas as pd
import json
from inception import Server, Service, InceptionTools
from pathlib import Path
from collections import Counter
import sys
import datetime
import os
import logging
import socket
import requests

app = Flask(__name__)


@app.route('/')
def main():
    return render_template('index.html')

@app.route('/<string:url_path>')
def path(url_path):
    return render_template(url_path)


@app.route('/count_service', methods=['POST','GET'])
def count_service():
   if request.method == 'POST':
      datacenter = request.form['Datacenter']
      environment = request.form['Environment']
      result = {}
      service_list = []

      data = InceptionTools(datacenter)
      work_fulldata = data.dc_data()

      for elements in work_fulldata['dynconfigMonitoringServerUrls']:
         for values in elements['url']:
            if elements['environment'] == environment:
               service_list.append(values['container'])
      count = Counter(service_list)
      counter = 0
      for key, value in count.items():
         if value < 3:
            counter += 1
            result[key] = str(value)
      return render_template('result.html', data=result)
      if counter == 0:
         return render_template('output.html', data='All services have 3 or more instances')


@app.route('/server-check', methods=['POST','GET'])
def server_check():
	if request.method == 'POST':
		datacenter = request.form['Datacenter']
		environment = request.form['Environment']
		inception_service = request.form['Service']

	if inception_service:
		service_data = inception_service.split(',')
		inception_request = Service(datacenter, environment)
		all_service = inception_request.specific_service()
		for content in service_data:
			if content not in all_service:
				return render_template('output.html',data = f'''FileNotFound Exception: Service {content} not found in {environment} environment.
		Please re-check service name''')
				sys.exit()
		inception_request = Server(datacenter, environment, service_data)
		return render_template('result-data.html', data = inception_request.specific_service())

	if datacenter:
		if bool(datacenter) ^ bool(environment):
			inception_request = Server(datacenter)
			return render_template('result-data.html', data = inception_request.all_server())
		else:
			inception_request = Server(datacenter, environment)
			return render_template('result-data.html', data = inception_request.specific_server())


DOCKER_COMMAND = 'docker ps -a --format "table {{.Names}}\t{{.Status}}"'
ERROR_WORDS = ['DOWN','NOT RUNNING','REBALANCING','UNKNOWN']
homeDir = os.getenv("HOME")
spaceFile = os.path.join(homeDir, 'health')
KEY = '/Users/nnarayanan/.ssh/id_rsa'
USERNAME = 'core'


class RemoteConnect:
	'''Class to peform SSH operations'''

	def __init__(self, server_name):
		try:
			self.ssh = SSHClient()
			self.ssh.load_system_host_keys()
			self.ssh.set_missing_host_key_policy(AutoAddPolicy())
			self.ssh.connect(hostname=server_name, 
							 username=USERNAME, 
							 key_filename=KEY)
		except (AuthenticationException,socket.timeout,socket.gaierror):
			print('SSHConnectionError: Failed to connect server\n')
			sys.exit()

	def run_command(self, command):
		if(self.ssh):
			stdin, stdout, stderr = self.ssh.exec_command(command)
			return stdout.read()
		else:
			print('Connection is not opened')


class ServiceCheck():
	'''Gathering endpoint status for inception service'''

	def __init__(self, service_name, dc_data, environment):
		self.service_name = service_name
		self.dc_data = dc_data
		self.environment = environment

	def service_url(self):
		service_url = []
		for element in self.dc_data['dynconfigMonitoringServerUrls']:
			for content in element['url']:
				if element['environment'] == self.environment and content['container'] == self.service_name:
					service_url.append(content['url'])
		return service_url


class ServicePrint(ServiceCheck):
	'''Class to handle print method efficiently'''

	def __init__(self, service_name, dc_data, environment):
		super().__init__(service_name, dc_data, environment)

	def gather_status(self, data):
		for word in ERROR_WORDS:
			if word not in str(data):
				continue
			else:
				contents.write('Service Status   : NOT READY')
				return
		if 'UP' or 'RUNNING' in str(data):
			contents.write('Service Status   : UP')
		else:
			contents.write(data)

	def info_print(self, data):
		if data:
			try:
				appname = 'Application Name : '+data['app']['name']
				appnumber = 'Build Number     : '+data['build']['number']
				apptime = 'Build Time       : '+data['build']['time']
				return appname, appnumber, apptime
			except KeyError:
				pass

	def endpoint_print(self, data):
		if data:
			try:
				contents.write('Service Status   : '+data['status'])	
			except (KeyError, TypeError):
				self.gather_status(data)

	def endpoint_check(self, url, check):
		try:
			responsedata = requests.get(url+'/'+check)
			full_data = json.loads(responsedata.text)

			return full_data
			
			self.info_print(full_data) if check == 'info' else self.endpoint_print(full_data)

		except json.decoder.JSONDecodeError:
			code_data = os.popen('curl -ks '+url+'/'+check).read()
			self.gather_status(code_data)
		except requests.exceptions.ConnectionError:
			contents.write('Exception: Not Ready Yet')



@app.route('/health-check', methods=['POST','GET'])
def health_check():
	if request.method == 'POST':
		datacenter = request.form['Datacenter']
		environment = request.form['Environment']
		inception_service = request.form['Service']

		os.remove(spaceFile)

		inception_request = InceptionTools(datacenter)
		dc_data = inception_request.dc_data()
		service_data = inception_service.split(',')

		for service in service_data:
			inception_request = ServicePrint(service, dc_data, environment)
			service_url = inception_request.service_url()
			with open(spaceFile, 'a+') as contents:
				contents.write('\n-----------------------SERVICE NAME: '+service+'-----------------------\n')
				contents.write("\n")
				for url in service_url:
					instance_name = url[7:-12]

					contents.write('-------INSTANCE NAME: '+instance_name+'\n')
					ssh_to = RemoteConnect(instance_name)
					common_url = url[:-6]

					contents.write('/INFO FOR: '+service+'\n')
					data = inception_request.endpoint_check(common_url, 'info')
					if data:
						try:
							contents.write('Application Name : '+data['app']['name']+'\n')
							contents.write('Build Number     : '+data['build']['number'+'\n'])
							contents.write('Build Time       : '+data['build']['time']+'\n')
						except KeyError:
							pass

					contents.write('/CHECK FOR: '+service+'\n')
					data = inception_request.endpoint_check(common_url, 'check')		
					if data:
						try:
							contents.write('Service Status   : '+data['status']+'\n')	
						except (KeyError, TypeError):
							contents.write('Service Status   : '+str(data)+'\n')


					contents.write('/HEALTH FOR: '+service+'\n')
					data = inception_request.endpoint_check(common_url, 'health')
					if data:
						try:
							contents.write('Service Status   : '+data['status']+'\n')
						except (TypeError, KeyError):
							contents.write('Service Status   : '+str(data)+'\n')


					contents.write('CONTAINER STATUS:'+'\n')
					container = ssh_to.run_command(DOCKER_COMMAND +'| grep '+service)
					if not container:
						contents.write('RunTimeException: Container {} is not running'.format(service))
					else:
						contents.write(container.decode('utf8').strip('\n'))
					contents.write('\n')
					contents.write("\n")

		with open(spaceFile, 'r') as contents:
			output = contents.read()
			output = output.replace('\n', '<br>')
			return render_template('output-health.html', data=output)
