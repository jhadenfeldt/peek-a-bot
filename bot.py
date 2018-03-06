# -*- coding: utf-8 -*-
import os
import shelve

from os.path import join, dirname
from dotenv import load_dotenv

dotenv_path = join(dirname(__file__), '.env')
load_dotenv(dotenv_path)

from slackclient import SlackClient

class Bot(object):

	def __init__(self):
		super(Bot, self).__init__()
		self.name = "Peek-a-Bot"

		self.oauth = {"client_id": os.environ.get("CLIENT_ID"),
					  "client_secret": os.environ.get("CLIENT_SECRET"),
					  "scope": "bot"}
		self.verification = os.environ.get("VERIFICATION_TOKEN")

		self.client = SlackClient("")

		self.messages = {}

	def auth(self, code):
		auth_response = self.client.api_call(
			"oauth.access",
			client_id=self.oauth["client_id"],
			client_secret=self.oauth["client_secret"],
			code=code
		)

		team_id = auth_response["team_id"]
		token = {"bot_token": auth_response["bot"]["bot_access_token"]}

		with shelve.open('../connections.db') as db:
			db[team_id] = {"bot_token": auth_response["bot"]["bot_access_token"]}

			db.close()

		self.client = SlackClient(token)


	def send_preview(self, channel, token, team_id, attachments):
		with shelve.open('../connections.db') as db:
			self.client = SlackClient(db[team_id]["bot_token"])
			db.close()

			self.client.api_call("chat.postMessage",
							 token=token,
							 channel=channel,
							 username=self.name,
							 attachments=attachments)

