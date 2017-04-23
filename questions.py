from bs4 import BeautifulSoup
import bs4
import os
import re
import pprint
import time
from pymongo import MongoClient
from utilities import generate_tfidf

from credentials import MONGO_URL

XML_DIR = os.path.join(os.path.dirname(__file__), 'xml')


def get_questions(house):
    decade = '1900'
    xml_path = os.path.join(XML_DIR, house)
    dirs = [d for d in os.listdir(xml_path) if (os.path.isdir(os.path.join(xml_path, d)) and d != 'missing')]
    for directory in dirs:
        current_decade = '{}0'.format(directory[:3])
        if decade != current_decade:
            decade = current_decade
        current_path = os.path.join(xml_path, directory)
        files = [f for f in os.listdir(current_path) if f[-4:] == '.xml']
        for file in files:
            with open(os.path.join(current_path, file), 'rb') as xml_file:
                soup = BeautifulSoup(xml_file.read(), 'lxml')
                header = soup.find('session.header')
                date = header.date.string.strip()
                print decade
                year, month, day = date.split('-')
                for index, debate in enumerate(soup.find_all('debate')):
                    if debate.debateinfo.type.string.strip() == 'Questions' or debate.title.string.strip() == 'QUESTION':
                        try:
                            question = debate.subdebateinfo.title.string.strip().encode('utf-8')
                        except AttributeError:
                            question = debate.title.string.strip().encode('utf-8')
                        debate_url = 'https://historichansard.net/{}/{}/{}/#debate-{}'.format(house, year, file[:-4], index)
                        with open('data/questions/{}/{}.txt'.format(house, decade), 'ab') as decade_file:
                            decade_file.write('{}\n'.format(question.lower()))

def tfidf_questions(house):
    data_dir = os.path.join(os.getcwd(), 'data', 'questions', house)
    generate_tfidf(data_dir, 1)