import os.path
import pickle
import base64
import json
import re
import time
import os
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import logging
import requests
from bs4 import BeautifulSoup

# email reader generator
class EmailRetriever(object):
    def __init__(self):
        self.count = 0
        self.creds = None
        
        self.cfg_path = 'retriever.cfg'
        self.unlabeled_path = './unlabeled'

        if not os.path.exists(self.unlabeled_path):
            os.makedirs(self.unlabeled_path)
        
        if os.path.exists(self.cfg_path):
            with open(self.cfg_path, 'rb') as f:
                self.seen_ids = pickle.load(f)
        else:
            self.seen_ids = set()

        if os.path.exists('./unlabeled/manifest.cfg'):
            with open('./unlabeled/manifest.cfg', 'r') as f:
                for line in f:
                    self.last_written_id = int(line)
                    break
        else:
            self.last_written_id = 0

        if os.path.exists('token.json'):
            self.creds = Credentials.from_authorized_user_file('token.json', SCOPES)

        if not self.creds or not self.creds.valid:
            if self.creds and self.creds.expired and self.creds.refresh_token:
                self.creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                        'my_cred_file.json', SCOPES)
                self.creds = flow.run_local_server(port=0)

                with open('token.json', 'w') as token:
                    token.write(self.creds.to_json())
        self.messages = None
        self.next_msg = 0

        self.max_msgs = 4 # for now for safety

    def __iter__(self):
        return self

    def __next__(self):
        return self.next()

    def cleanup(self):
        with open(self.cfg_path, 'wb') as f: # dump the dictionary
            pickle.dump(self.seen_ids, f)
        with open('./unlabeled/manifest.cfg', 'w') as f:
            f.write('{}'.format(self.last_written_id))

    def next(self):
        if (self.count >= self.max_msgs):
            print('reached max messages')
            self.cleanup()
            raise StopIteration()

        if self.messages is None or self.next_msg == len(self.messages): # go get more
            self.next_msg = 0
            try:
                self.service = build('gmail', 'v1', credentials=self.creds) #, q='is:unread'
                results = self.service.users().messages().list(userId='me', labelIds=['INBOX']).execute()
                self.messages = results.get('messages', [])
                print('got messages')
                if not self.messages:
                    print('No new messages')
                    self.cleanup()
                    raise StopIteration() 
            except Exception as error:
                print(f'An eror occurred: {error}')
        message = self.messages[self.next_msg]
        self.next_msg += 1
        new_id = message['id']
        print(message)

        if new_id in self.seen_ids:
            print('encountered old message')
            self.next_msg += 1
            return self.next()
        
        self.count += 1
        msg = self.service.users().messages().get(userId='me', id=message['id']).execute()

        read = 'UNREAD' not in msg['labelIds']
        read_token = 'r' if read else 'u'

        email_data = msg['payload']['headers']
        for values in email_data:
            name = values['name']
            if name == 'From':
                from_name = values['value']
                
                if 'parts' in msg['payload']:
                    d = msg['payload']['parts']
                elif 'body' in msg['payload']:
                    d = msg['payload']['body']                

                for part in d:
                    try:
                        data = part['body']["data"]
                        byte_code = base64.urlsafe_b64decode(data)

                        text = byte_code.decode('utf-8')
                        self.seen_ids.add(new_id)
                        self.last_written_id += 1
                        if '<!' in text[:5]: # suspected HTML lets clean this up
                            bs = BeautifulSoup(text, 'html.parser')
                            text = str(bs.get_text())
                        else:
                            text = str(text)
                        print(text[:100])
                        with open('./unlabeled/{}_unlabeled_{}.txt'.format(read_token, self.last_written_id), 'w') as f:
                            print('writing')
                            f.write(text)
                        return text 
                    except BaseException as error:
                        pass

SCOPES = ['https://www.googleapis.com/auth/gmail.readonly'] #,'https://www.googleapis.com/auth/gmail.modify']

def readEmails():
    """Shows basic usage of the Gmail API.
    Lists the user's Gmail labels.
    """
    creds = None
    # The file token.json stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first
    # time.
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(               
                # your creds file here. Please create json file as here https://cloud.google.com/docs/authentication/getting-started
                'my_cred_file.json', SCOPES)
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
    try:
        # Call the Gmail API
        service = build('gmail', 'v1', credentials=creds)# q="is:unread"
        results = service.users().messages().list(userId='me', labelIds=['INBOX']).execute()
        messages = results.get('messages',[]);
        if not messages:
            print('No new messages.')
        else:
            message_count = 0
            for message in messages:
                if message_count > 50:
                    break
                message_count += 1
                msg = service.users().messages().get(userId='me', id=message['id']).execute()                
                if ('unread' in message['labelIds']):
                    print('unread message!')
                else:
                    print("not unread!")
                email_data = msg['payload']['headers']
                for values in email_data:
                    name = values['name']
                    print('here')
                    if name == 'From':
                        from_name= values['value']                
                        for part in msg['payload']['parts']:
                            try:
                                data = part['body']["data"]
                                byte_code = base64.urlsafe_b64decode(data)

                                text = byte_code.decode("utf-8")
                                if "<!" in text[:5]:
                                    bs = BeautifulSoup(text, "html.parser")
                                    print("This is the message2: " + str(bs.get_text()))
                                else:
                                    print ("This is the message: "+ str(text))

                                # mark the message as read (optional)
                                # msg  = service.users().messages().modify(userId='me', id=message['id'], body={'removeLabelIds': ['UNREAD']}).execute()                                                       
                            except BaseException as error:
                                print('base exception')
                                pass                            
    except Exception as error:
        print(f'An error occurred: {error}')

# readEmails()

e = EmailRetriever()

for x in e:
    print("EMAIL")
