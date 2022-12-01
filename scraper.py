import os.path
import pickle
import base64
import json
import re
import time
import os
import shutil
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import logging
import requests
from bs4 import BeautifulSoup

SCOPES = ['https://www.googleapis.com/auth/gmail.readonly'] #,'https://www.googleapis.com/auth/gmail.modify']

# email reader generator
class EmailRetriever(object):
    def __init__(self):
        print('-'*50)
        t = time.strftime('%m/%d/%Y, %H:%M:%S')
        print('running scraper at {}'.format(t))
        self.count = 0
        self.creds = None
        
        self.cfg_path = 'retriever.cfg'
        self.unlabeled_path = './unlabeled'

        if not os.path.exists(self.unlabeled_path):
            os.makedirs(self.unlabeled_path)

        if not os.path.exists('./unlabeled/read'):
            os.makedirs('./unlabeled/read')

        if not os.path.exists('./unlabeled/unread'):
            os.makedirs('./unlabeled/unread')
        
        if os.path.exists(self.cfg_path):
            with open(self.cfg_path, 'rb') as f:
                self.seen_unread_ids, self.seen_read_ids, self.first_id = pickle.load(f)
            print('first id: ', self.first_id)
        else:
            self.seen_unread_ids = set()
            self.seen_read_ids = set()
            self.first_id = None 
        
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

        self.max_msgs = 50 # per retrieval cycle -> up to 50 emails a day
    
    def __iter__(self):
        return self

    def __next__(self):
        return self.next()

    def cleanup(self):
        with open(self.cfg_path, 'wb') as f: # dump the dictionary
            pickle.dump((self.seen_unread_ids, self.seen_read_ids, self.first_id), f)

    def next(self):
        def hr_to_label(hr):
            hr = int(hr)

            if 6 <= hr and hr < 11: # morning
                return 'morn'
            elif 11 <= hr and hr < 16: # midday 
                return 'noon'
            elif 16 <= hr and hr < 21: # evening
                return 'even'
            elif 21 <= hr or hr < 2: # night time
                return 'night'
            else: # late night
                return 'late'

        if (self.count >= self.max_msgs):
            print('reached max messages')
            self.cleanup()
            raise StopIteration()

        keep_going = True
        while (keep_going):
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

            # TODO: add timesstamps
            if new_id == self.first_id:
                print('saw first')
                self.cleanup()
                raise StopIteration()
            elif new_id in self.seen_unread_ids:
                print('got seen unread')
                msg = self.service.users().messages().get(userId='me', id=message['id']).execute()
                read = 'UNREAD' not in msg['labelIds']
                
                if read:
                    self.seen_unread_ids.remove(new_id)
                    self.seen_read_ids.add(new_id)
                    hr = time.strftime('%H') # get current hr
                    label = hr_to_label(hr)
                    # move dumped file
                    shutil.move('./unlabeled/unread/unlabeled_{}.txt'.format(new_id), './unlabeled/read/unlabeled_{}.txt'.format(new_id))

                    # add label by prepending a line
                    with open('./unlabeled/read/unlabeled_{}.txt'.format(new_id), 'r') as f:
                        old_snippet = f.read()
                    with open('./unlabeled/read/unlabeled_{}.txt'.format(new_id), 'w') as f:
                        f.write('{}\n'.format(label) + old_snippet) 

                    print('moving file')

                keep_going = True
            elif new_id in self.seen_read_ids: # done all we can with this one
                print('got seen read')
                keep_going = True
            else:
                print('got fresh')
                keep_going = False

            print(message)

        #if new_id in self.seen_ids:
        #    print('encountered old message')
        #    self.next_msg += 1
        #    return self.next()
        print('fell through')

        if self.first_id is None:
            self.first_id = new_id
        
        msg = self.service.users().messages().get(userId='me', id=message['id']).execute()

        read = 'UNREAD' not in msg['labelIds']
        read_token = 'r' if read else 'u'

        email_data = msg['snippet'] # we use just the snippet as enough information 

        if read:
            self.seen_read_ids.add(new_id)
        else:
            self.seen_unread_ids.add(new_id)

        self.count += 1

        print('snippet: ', email_data)

        hr = time.strftime('%H')
        label = hr_to_label(hr)
        if (read):
            with open('./unlabeled/read/unlabeled_{}.txt'.format(new_id), 'w') as f:
                f.write('{}\n'.format(label) + email_data)
                return email_data
        else:
            with open('./unlabeled/unread/unlabeled_{}.txt'.format(new_id), 'w') as f:
                f.write(email_data)
                return email_data
        #for values in email_data:
        #    name = values['name']
        #    if name == 'From':
        #        from_name = values['value']
        #        
        #        if 'parts' in msg['payload']:
        #            print('type 1')
        #            d = msg['payload']['parts']
        #        elif 'body' in msg['payload']:
        #            print('type 2')
        #            d = msg['payload']['body']                
        #        #print(d)
        #        for part in d:
        #            #print('here')
        #            #print(part)
        #            try:
        #                data = part['body']["data"]

        #                print('data: ', data)
        #                return ''
        #                byte_code = base64.urlsafe_b64decode(data)

        #                text = byte_code.decode('utf-8')

        #                if (read):
        #                    self.seen_read_ids(new_id)
        #                else:
        #                    self.seen_unread_ids(new_id)

        #                self.count += 1 # a new understandable message
        #                self.last_written_id += 1
        #                if '<!' in text[:5]: # suspected HTML lets clean this up
        #                    print('html')
        #                    bs = BeautifulSoup(text, 'html.parser')
        #                    text = str(bs.get_text())
        #                else:
        #                    text = str(text)

        #                if (read):
        #                    with open('./unlabeled/read/unlabeled_{}.txt'.format(self.last_written_id), 'w') as f:
        #                        print('writing')
        #                        f.write(text)
        #                    return text 
        #                else:
        #                    with open('./unlabeled/unread/unlabeled_{}.txt'.format(self.last_written_ids), 'w') as f:
        #                        f.write(text)
        #                        print('writing unread')
        #                    return text
        #            except BaseException as error:
        #                print('base exception')
        #                self.ignore_ids.add(new_id)
        #                pass


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
print('Got {} emails'.format(e.count))
