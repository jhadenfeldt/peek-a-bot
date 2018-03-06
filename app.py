# -*- coding: utf-8 -*-
import bot

import json
import hashlib
import requests
import os
import asyncio
import tinys3

from flask import Flask, request, make_response, render_template, send_from_directory, send_file
from pyppeteer.launcher import launch
from os.path import join, dirname
from dotenv import load_dotenv
from threading import Thread

dotenv_path = join(dirname(__file__), '.env')
load_dotenv(dotenv_path)

pyBot = bot.Bot()
slack = pyBot.client

conn = tinys3.Connection(os.environ.get("S3_SECRET"), os.environ.get("S3_KEY"), tls=True, default_bucket='peek-a-bot')

app = Flask(__name__)


def start_screenshot_worker(loop):
	asyncio.set_event_loop(loop)
	loop.run_forever()


worker_loop = asyncio.new_event_loop()
worker = Thread(target=start_screenshot_worker, args=(worker_loop,))

worker.start()


async def create_screenshot(config, response_url):
	# Send the first response to let the user know the screenshot is being generated
	payload = {
		"username": "Peek-a-Bot",
		"text": "One moment please, I'm generating the screenshot."
	}

	requests.post(response_url, data=json.dumps(payload))

	browser = launch(headless=True, options={"ignoreHTTPSErrors": True})
	page = await browser.newPage()

	await page.setViewport({
		"width": config["width"],
		"height": config["height"]
	});

	await page.goto(config["url"])

	filename = hashlib.sha256((os.environ.get("FILENAME_SALT") + config["url"] + str(config["width"]) + str(
		config["height"]) + str(config["fullPage"])).encode('utf-8')).hexdigest()
	filepath = 'data/{url}.jpg'.format(url=filename)
	await page.screenshot({'path': filepath, 'fullPage': config["fullPage"]})

	await browser.close()

	# Upload the file to S3 and delete the local temp file
	file = open(filepath, 'rb')
	response = conn.upload(filepath, file)
	os.unlink(filepath)

	# Send the second response with the screenshot to the user
	payload = {
		"username": "Peek-a-Bot",
		"text": "Here you go:",
		"attachments": [{
			"text": config["url"],
			"image_url": "{S3_INSTANCE}/{filepath}".format(S3_INSTANCE=os.environ.get("S3_INSTANCE"), filepath=filepath)
		}]
	}

	requests.post(response_url, data=json.dumps(payload))


def parse_parameters(param_string):
	param_array = param_string.split()

	# Add http-protocol in case the user didn't provide one
	if (not param_array[0].startswith('http://') and not param_array[0].startswith('https://')):
		param_array[0] = 'http://' + param_array[0]

	parameters = {
		"url": param_array[0],
		"fullPage": False
	}

	# Set the correct size parameters depending on the user input
	parameters["width"] = 1920
	if (len(param_array) > 1):
		if (param_array[1].isdigit()):
			parameters["width"] = int(param_array[1])
		else:
			if (param_array[1] == "all"):
				parameters["fullPage"] = True

	if (len(param_array) > 2):
		parameters["height"] = int(param_array[2])
	else:
		parameters["height"] = 1080

	return parameters


@app.route("/install", methods=["GET"])
def pre_install():
	client_id = pyBot.oauth["client_id"]
	scope = pyBot.oauth["scope"]

	return render_template("install.html", client_id=client_id, scope=scope)


@app.route("/thanks", methods=["GET", "POST"])
def thanks():
	code_arg = request.args.get('code')
	pyBot.auth(code_arg)

	return render_template("thanks.html")


@app.route("/listening", methods=["GET", "POST"])
def hears():
	slack_event = json.loads(request.data)

	if "challenge" in slack_event:
		return make_response(slack_event["challenge"], 200, {"content_type": "application/json"})

	if pyBot.verification != slack_event.get("token"):
		message = "Invalid Slack verification token: %s \npyBot has: \
                   %s\n\n" % (slack_event["token"], pyBot.verification)

	return make_response("[NO EVENT IN SLACK REQUEST]", 404, {"X-Slack-No-Retry": 1})


@app.route("/peek", methods=["GET", "POST"])
def peeks():
	if (request.form):
		response_url = request.form["response_url"]
		screenshot_parameters = parse_parameters(request.form["text"])
		worker_loop.call_soon_threadsafe(asyncio.async, create_screenshot(screenshot_parameters, response_url))

	return ('', 204)


if __name__ == '__main__':
	app.run(debug=False,ssl_context='adhoc')
