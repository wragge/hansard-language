from bs4 import BeautifulSoup
import bs4
import os
import re
import pprint
import time
from datetime import datetime
from pymongo import MongoClient, TEXT
from pymongo.errors import DuplicateKeyError
import nltk
from nltk.collocations import *
from nltk.corpus.reader.plaintext import PlaintextCorpusReader
from textblob import TextBlob
from collections import defaultdict, Counter
from operator import itemgetter
from utilities import generate_tfidf
from wordcloud import WordCloud
import random
import plotly.plotly as py
import plotly.graph_objs as go
from sklearn.feature_extraction.text import TfidfVectorizer
import csv

from credentials import MONGO_URL

XML_DIR = os.path.join(os.path.dirname(__file__), 'xml')
PARLIAMENTS = [str(p) for p in range(1, 33)]
HOUSES = ['hofreps', 'senate']
YEARS = [str(y) for y in range(1901, 1981)]
try:
    STOPWORDS = nltk.corpus.stopwords.words('english')
except LookupError:
    pass
HOUSE_NAMES = {'hofreps': 'House of Representatives', 'senate': 'Senate'}


WORDs = [
    'community',
    'individualism',
    'revolution',
    'modernisation',
    'crisis',
    'white australia',
    'immigration',
    'multiculturalism',
    'britishness',
    'aborigines',
    'freedoms',
    'welfare',
    'tyranny',
    'social experiment',
    'federation',
    'states',
    'alliance',
    'independence',
    'decolonisation',
    'arms race',
    'papua new guinea'
]

LIST_TYPES = {
    'loweralpha': 'a',
    'loweralpha-dotted': 'a',
    'decimal': '1',
    'decimal-dotted': '1',
    'upperalpha-dotted': 'A',
    'upperalpha': 'A',
    'lowerroman-dotted': 'i',
    'lowerroman': 'i',
    'upperroman': 'I',
    'upperroman-dotted': 'I',
}


def get_speaker_details(talk):
    speaker = {}
    # details = []
    speaker['name'] = talk.talker.find('name', role='display').string.strip()
    try:
        speaker['display_name'] = talk.talker.find('name', role='metadata').string.strip()
    except AttributeError:
        pass
    # speaker['page'] = talk.talker.find('page.no').string.encode('utf-8')
    speaker['id'] = talk.talker.find('name.id').string
    fields = ['role', 'electorate', 'party']
    for field in fields:
        try:
            speaker[field] = talk.talker.find(field).string.strip()
            # details.append(talk.talker.find(field).string.strip())
        except AttributeError:
            pass
    # speaker['details'] = ' &middot; '.join(details)
    return speaker


def format_continue(part):
    text = []
    speaker = get_speaker_details(part.find('talk.start'))
    for para in part.find_all('para'):
        text.append(convert_text(para))
    speaker['text'] = text
    return speaker


def format_quote(part):
    text = []
    for para in part.find_all('para'):
        text.append('  >{}'.format(convert_text(para)))
    return text


def format_list(part):
    text = []
    for para in part.find_all('para'):
        text.append('  * {}'.format(convert_text(para)))
    return text


def convert_text(para):
    # Change inital hypen to ndash.
    text = str(para).replace('<para>', '').replace('<para class="block">', '').replace('</para>', '').replace('<para class="italic">', '')
    text = text.replace('|', '')  # Pipes can cause tables
    text = re.sub(r'^- ', '', text)
    text = re.sub(r'^\. - ', '', text)
    text = text.replace('{', '(').replace('}', ')')
    text = text.replace('\\', '')
    text = re.sub(r'\<inline font\-style\="italic"\>(.+?)\<\/inline\>', r' \1 ', text)
    text = re.sub(r'\<inline font\-weight\="bold"\>(.+?)\<\/inline\>', r' \1 ', text)
    return text


def get_text(section):
    text = []
    for part in [c for c in section.children if type(c) == bs4.element.Tag]:
        if part.name == 'talk.start':
            speaker = get_speaker_details(part)
            for para in part.find_all('para', recursion=False):
                text.append(convert_text(para))
        elif part.name == 'para':
            text.append(convert_text(part))
        elif part.name in ['continue', 'interjection']:
            cont = format_continue(part)
            if cont['id'] == speaker['id']:
                text += cont['text']
            else:
                if cont['id'] not in speakers:
                    speakers[cont['id']] = cont
                else:
                    speakers[cont['id']]['text'] += cont['text']
        elif part.name == 'quote':
            text += format_quote(part)
        elif part.name == 'list':
            text += format_list(part)
    return text


def get_speeches_by_bill(house, bill_titles, years=None):
    debates = []
    xml_path = os.path.join(XML_DIR, house)
    if years:
        dirs = [d for d in os.listdir(xml_path) if (os.path.isdir(os.path.join(xml_path, d)) and d in years)]
    else:
        dirs = [d for d in os.listdir(xml_path) if (os.path.isdir(os.path.join(xml_path, d)) and d != 'missing')]
    for directory in dirs:
        current_path = os.path.join(xml_path, directory)
        files = [f for f in os.listdir(current_path) if f[-4:] == '.xml']
        # with open(os.path.join(md_path, 'index.md'), 'w') as index_file:
        #    write_frontmatter(index_file, directory)
        for file in files:
            with open(os.path.join(current_path, file), 'rb') as xml_file:
                soup = BeautifulSoup(xml_file.read(), 'lxml')
                for debate in soup.find_all('debate'):
                    title = debate.debateinfo.title.string.encode('utf-8')
                    if title.lower() in bill_titles:
                        header = soup.find('session.header')
                        date = header.date.string
                        day = {'date': date}
                        speakers = {}
                        print date
                        for section in debate.find_all('speech'):
                            text = []
                            for part in [c for c in section.children if type(c) == bs4.element.Tag]:
                                if part.name == 'talk.start':
                                    speaker = get_speaker_details(part)
                                    for para in part.find_all('para', recursion=False):
                                        text.append(convert_text(para))
                                elif part.name == 'para':
                                    text.append(convert_text(part))
                                elif part.name in ['continue', 'interjection']:
                                    cont = format_continue(part)
                                    if cont['id'] == speaker['id']:
                                        text += cont['text']
                                    else:
                                        if cont['id'] not in speakers:
                                            speakers[cont['id']] = cont
                                        else:
                                            speakers[cont['id']]['text'] += cont['text']
                                elif part.name == 'quote':
                                    text += format_quote(part)
                                elif part.name == 'list':
                                    text += format_list(part)
                            if speaker['id'] not in speakers:
                                speaker['text'] = text
                                speakers[speaker['id']] = speaker
                            else:
                                speakers[speaker['id']]['text'] += text
                        day['speakers'] = speakers
                        debates.append(day)
    pprint.pprint(debates)


def get_stats(house):
    total_words = 0
    total_files = 0
    xml_path = os.path.join(XML_DIR, house)
    dirs = [d for d in os.listdir(xml_path) if (os.path.isdir(os.path.join(xml_path, d)) and d != 'missing')]
    for directory in dirs:
        year_words = 0
        current_path = os.path.join(xml_path, directory)
        files = [f for f in os.listdir(current_path) if f[-4:] == '.xml']
        # with open(os.path.join(md_path, 'index.md'), 'w') as index_file:
        #    write_frontmatter(index_file, directory)
        for file in files:
            total_files += 1
            with open(os.path.join(current_path, file), 'rb') as xml_file:
                soup = BeautifulSoup(xml_file.read(), 'lxml')
                for speech in soup.find_all('speech'):
                    for para in speech.find_all('para'):
                        text = convert_text(para)
                        year_words += len(re.split('\s+', text))
        print '{}: {}'.format(directory, year_words)
        total_words += year_words
    print 'Total files: {}'.format(total_files)
    print 'Total: {}'.format(total_words)


def get_speech_totals(house):
    speeches = 0
    questions = 0
    total_files = 0
    xml_path = os.path.join(XML_DIR, house)
    dirs = [d for d in os.listdir(xml_path) if (os.path.isdir(os.path.join(xml_path, d)) and d != 'missing')]
    for directory in dirs:
        year_speeches = 0
        year_questions = 0
        current_path = os.path.join(xml_path, directory)
        files = [f for f in os.listdir(current_path) if f[-4:] == '.xml']
        for file in files:
            total_files += 1
            with open(os.path.join(current_path, file), 'rb') as xml_file:
                soup = BeautifulSoup(xml_file.read(), 'lxml')
                for debate in soup.find_all('debate'):
                    debate_type = debate.debateinfo.type.string
                    if debate_type == 'Questions':
                        year_questions += 1
                    else:
                        year_speeches += len(debate.find_all('speech'))
        print '{}: {} speeches, {} questions'.format(directory, year_speeches, year_questions)
        speeches += year_speeches
        questions += year_questions
    print 'Total speeches: {}'.format(speeches)
    print 'Total questions: {}'.format(questions)
    print 'Total files: {}'.format(total_files)


# Want to load individual speeches into a database.
# Each speech belongs to a speaker and is part of a debate
# Speeches can be within speeches (interjections, questions and answers)
# Each speech is made of parts (paragraphs, quotes, lists)
# Loop through days -> debates -> speakers -> parts
# Context: House, date, parliament, debate, speaker
# Possible context: subdebate, speech (if interjection)
# questions upon notice have <question> and <answer> <answers.to.questions> -> debates -> subdebates -> question
# subdebates contain individual questions -- so the q is in subdebateinfo.title (I think you could ignore debates, seems redundant)
# Normal questions are subdebates -- questions and answers are separate speeches


def get_paras(part):
    text = []
    for para in part.find_all('para'):
        text.append(convert_text(para))
    return text


def process_speech(speech):
    text = []
    for part in [c for c in speech.children if type(c) == bs4.element.Tag]:
        if part.name == 'talk.start':
            speaker = get_speaker_details(part)
            for para in part.find_all('para', recursion=False):
                text.append(convert_text(para))
        elif part.name == 'para':
            text.append(convert_text(part))
        elif part.name in ['continue', 'interjection']:
            cont = format_continue(part)
            if cont['id'] == speaker['id']:
                text += cont['text']
            # else:
                # if these are <continue> then it's probably the Speaker
                # if cont['id'] not in speakers:
                #    speakers[cont['id']] = cont
                # else:
                #    speakers[cont['id']]['text'] += cont['text']
        elif part.name in ['quote', 'list', 'motion']:
            text += get_paras(part)
    return {'speaker': speaker, 'text': text}


def load_speeches(house, decade=None):
    dbclient = MongoClient(MONGO_URL)
    db = dbclient.get_default_database()
    xml_path = os.path.join(XML_DIR, house)
    if decade:
        dirs = [d for d in os.listdir(xml_path) if (os.path.isdir(os.path.join(xml_path, d)) and d != 'missing' and d[:3] == decade)]
    else:
        dirs = [d for d in os.listdir(xml_path) if (os.path.isdir(os.path.join(xml_path, d)) and d != 'missing')]
    for directory in dirs:
        current_path = os.path.join(xml_path, directory)
        files = [f for f in os.listdir(current_path) if f[-4:] == '.xml']
        for file in files:
            speeches = []
            with open(os.path.join(current_path, file), 'rb') as xml_file:
                soup = BeautifulSoup(xml_file.read(), 'lxml')
                day = soup.find('session.header').date.string.strip()
                parliament = soup.find('session.header').find('parliament.no').string.strip()
                for debate_index, debate in enumerate(soup.find_all('debate')):
                    debate_title = debate.debateinfo.title.string.strip()
                    try:
                        debate_type = debate.debateinfo.type.string.strip()
                    except AttributeError:
                        pass
                    # get speeches that are direct children
                    for speech_index, section in enumerate(debate.find_all('speech', recursive=False)):
                        speech = process_speech(section)
                        speech['speech_index'] = speech_index
                        speech['house'] = house
                        speech['date'] = day
                        speech['year'] = day[:4]
                        speech['decade'] = '{}0'.format(day[:3])
                        speech['parliament'] = parliament
                        speech['debate_index'] = debate_index
                        speech['debate_title'] = debate_title
                        speech['debate_type'] = debate_type
                        speeches.append(speech)
                    for subdebate_index, subdebate in enumerate(debate.find_all(re.compile("^subdebate\."))):
                        subdebate_title = subdebate.subdebateinfo.title.string.strip()
                        for speech_index, section in enumerate(subdebate.find_all(['speech', 'question', 'answer'])):
                            speech = process_speech(section)
                            speech['speech_index'] = speech_index
                            speech['house'] = house
                            speech['date'] = day
                            speech['date'] = day
                            speech['year'] = day[:4]
                            speech['decade'] = '{}0'.format(day[:3])
                            speech['parliament'] = parliament
                            speech['debate_index'] = debate_index
                            speech['debate_title'] = debate_title
                            speech['debate_type'] = debate_type
                            speech['subdebate_title'] = subdebate_title
                            speech['subdebate_index'] = subdebate_index
                            speeches.append(speech)
            #pprint.pprint(speeches)
            try:
                db.speeches.insert_many(speeches)
            except TypeError:
                print '{} - no speeches'.format(day)


def add_filenames(house):
    '''Because I should have done this when I loaded the speeches...'''
    dbclient = MongoClient(MONGO_URL)
    db = dbclient.get_default_database()
    xml_path = os.path.join(XML_DIR, house)
    dirs = [d for d in os.listdir(xml_path) if (os.path.isdir(os.path.join(xml_path, d)) and d != 'missing')]
    for directory in dirs:
        print directory
        current_path = os.path.join(xml_path, directory)
        files = [f for f in os.listdir(current_path) if f[-4:] == '.xml']
        for file in files:
            with open(os.path.join(current_path, file), 'rb') as xml_file:
                soup = BeautifulSoup(xml_file.read(), 'lxml')
                day = soup.find('session.header').date.string.strip()
                # print '{} - {}'.format(day, file[:-4])
                db.speeches.update_many({'date': day, 'house': house}, {'$set': {'filename': file[:-4]}})
                soup.decompose()


def stopwords_check(ngram):
    ''' Check if all words in ngrams are stopwords '''
    keep = False
    for word in ngram:
        if word not in STOPWORDS:
            keep = True
            break
    return keep


def add_ngrams(decade, house):
    ''' If I do this again I should add this to load_speeches... '''
    dbclient = MongoClient(MONGO_URL)
    db = dbclient.get_default_database()
    speeches = db.speeches.find({'decade': decade, 'house': house, 'words': {'$exists': False}}).batch_size(10)
    for index, speech in enumerate(speeches):
        text = ' '.join(speech['text'])
        blob = TextBlob(text)
        words = [{'w': word.lower(), 'c': count, 'l': 1} for word, count in blob.word_counts.items() if word not in STOPWORDS]
        bigrams = [' '.join(bigram).lower() for bigram in blob.ngrams(2) if stopwords_check(bigram)]
        words += [{'w': word, 'c': count, 'l': 2} for word, count in Counter(bigrams).items()]
        trigrams = [' '.join(trigram).lower() for trigram in blob.ngrams(3) if stopwords_check(trigram)]
        words += [{'w': word, 'c': count, 'l': 3} for word, count in Counter(trigrams).items()]
        db.speeches.update_one({'_id': speech['_id']}, {'$set': {'words': words}})
        if not index % 10:
            print index


def word_frequency(word, house, decade):
    '''
    The frequency of a word or phrase per day.
    '''
    dbclient = MongoClient(MONGO_URL)
    db = dbclient.get_default_database()
    pipeline = [
        {'$match': {'words.w': word, 'decade': decade, 'house': house}},
        {'$group': {'_id': '$date', 'words': {'$push': {'$filter': {'input': '$words', 'as': 'word', 'cond': {'$eq': ['$$word.w', word]}}}}}},
        {'$unwind': '$words'},
        {'$unwind': '$words'},
        {'$group': {'_id': '$_id', 'count': {'$sum': '$words.c'}}},
        {'$project': {'_id': 0, 'date': '$_id', 'count': 1}},
        {'$sort': {'date': 1}}
    ]
    results = db.speeches.aggregate(pipeline)
    return results


def list_people(house=None, decade=None, parliament=None, party=None):
    dbclient = MongoClient(MONGO_URL)
    db = dbclient.get_default_database()
    query = {'_id': {'$nin': ['10000', '20000']}}  # Speaker, President
    if house:
        query['house'] = house
    if decade:
        query['decade'] = decade
    if parliament:
        query['parliament'] = parliament
    if party:
        query['speaker.party'] = party
    pipeline = [
        {'$match': query},
        {'$group': {'_id': '$speaker.id', 'names': {'$addToSet': "$speaker.name"}, 'display_names': {'$addToSet': "$speaker.display_name"}, 'parties': {'$addToSet': "$speaker.party"}}}
    ]
    people = db.speeches.aggregate(pipeline)
    #pprint.pprint(list(people))
    return people


def load_people(house):
    dbclient = MongoClient(MONGO_URL)
    db = dbclient.get_default_database()
    people = list_people(house)
    for person in people:
        try:
            db.people.insert_one(person)
            print 'Added {}'.format(person['_id'])
        except DuplicateKeyError:
            pass


def list_parties(house, decade=None, parliament=None):
    dbclient = MongoClient(MONGO_URL)
    db = dbclient.get_default_database()
    query = {'house': house}
    if decade:
        query['decade'] = decade
    if parliament:
        query['parliament'] = parliament
    pipeline = [
        {'$match': query},
        {'$group': {'_id': {'id': '$speaker.party'}, 'count': {'$sum': 1}}}
    ]
    parties = list(db.speeches.aggregate(pipeline))
    pprint.pprint(parties)


def write_speeches_by_person(house=None, decade=None, parliament=None):
    dbclient = MongoClient(MONGO_URL)
    db = dbclient.get_default_database()
    query = {'_id': {'$nin': ['10000', '20000']}}
    if house:
        query['house'] = house
    if decade:
        query['decade'] = decade
    if parliament:
        query['parliament'] = parliament
    pipeline = [
        {'$match': query},
        {'$group': {'_id': '$speaker.id', 'names': {'$addToSet': "$speaker.display_name"}, 'other_names': {'$addToSet': "$speaker.name"}}}
    ]
    people = db.speeches.aggregate(pipeline)
    for person in people:
        try:
            person_name = person['names'][0]
            for name in person['names']:
                if not re.search(r'SPEAKER|CHAIRMAN', name):
                    person_name = name
                    break
        except IndexError:
            person_name = person['other_names'][0]
            for name in person['other_names']:
                if not re.search(r'SPEAKER|CHAIRMAN', name):
                    person_name = name
                    break
        try:
            filename = '{}-{}.txt'.format(person['_id'], person_name.lower().replace(', ', '-').replace(' ', '-'))
        except UnicodeEncodeError:
            filename = '{}-{}.txt'.format(person['_id'], "".join(i for i in person_name.lower().replace(' ', '-').replace('.', '-') if ord(i) < 128))
        with open(os.path.join('data', 'speeches', 'people', filename), 'wb') as text_file:
            query = {'speaker.id': person['_id']}
            if house:
                query['house'] = house
            if decade:
                query['decade'] = decade
            if parliament:
                query['parliament'] = parliament
            speeches = db.speeches.find(query).sort('date')
            for speech in speeches:
                for para in speech['text']:
                    text_file.write('{}\n'.format(para.encode('utf-8')))


def write_speeches_by_year():
    dbclient = MongoClient(MONGO_URL)
    db = dbclient.get_default_database()
    for house in HOUSES:
        for year in YEARS:
            speeches = db.speeches.find({'house': house, 'year': year}).sort('date')
            with open(os.path.join('data', 'speeches', 'years', house, '{}.txt'.format(year)), 'ab') as text_file:
                for speech in speeches:
                    for para in speech['text']:
                        text_file.write('{}\n'.format(para.encode('utf-8')))


def write_speeches_by_parliament():
    dbclient = MongoClient(MONGO_URL)
    db = dbclient.get_default_database()
    for house in HOUSES:
        for parliament in PARLIAMENTS:
            speeches = db.speeches.find({'house': house, 'parliament': parliament}).sort('date')
            with open(os.path.join('data', 'speeches', 'parliaments', house, '{}.txt'.format(parliament)), 'ab') as text_file:
                for speech in speeches:
                    for para in speech['text']:
                        text_file.write('{}\n'.format(para.encode('utf-8')))


def write_speeches_by_decade():
    dbclient = MongoClient(MONGO_URL)
    db = dbclient.get_default_database()
    for house in HOUSES:
        for decade in range(1900, 1990, 10):
            speeches = db.speeches.find({'house': house, 'decade': str(decade)}).sort('date')
            with open(os.path.join('data', 'speeches', 'decades', house, '{}.txt'.format(decade)), 'ab') as text_file:
                for speech in speeches:
                    for para in speech['text']:
                        text_file.write('{}\n'.format(para.encode('utf-8')))


def find_collocations(word, house, decade):
    bigram_measures = nltk.collocations.BigramAssocMeasures()
    trigram_measures = nltk.collocations.TrigramAssocMeasures()

    with open(os.path.join('data', 'speeches', 'decades', house, '{}.txt'.format(decade)), 'rb') as text_file:
        text = text_file.read().decode('ascii', errors="ignore")
        blob = TextBlob(text)
    # Ngrams with 'creature' as a member
    word_filter = lambda *w: word not in w
    # Bigrams
    finder = BigramCollocationFinder.from_words(blob.words)
    # only bigrams that appear 3+ times
    finder.apply_freq_filter(3)
    # only bigrams that contain 'creature'
    finder.apply_ngram_filter(word_filter)
    # return the 10 n-grams with the highest PMI
    print finder.nbest(bigram_measures.likelihood_ratio, 10)
    # Trigrams
    finder = TrigramCollocationFinder.from_words(blob.words)
    # only trigrams that appear 3+ times
    finder.apply_freq_filter(3)
    # only trigrams that contain 'creature'
    finder.apply_ngram_filter(word_filter)
    # return the 10 n-grams with the highest PMI
    print finder.nbest(trigram_measures.likelihood_ratio, 10)


def word_summary(word, decade):
    if len(word.split()) == 1:
        query_type = 'word'
    else:
        query_type = 'phrase'
    results_dir = os.path.join('docs', '_words', word.replace(' ', '-').strip('"'))
    if not os.path.exists(results_dir):
        os.makedirs(results_dir)
    with open(os.path.join(results_dir, 'index.html'), 'wb') as index_file:
        index_file.write('---\n')
        index_file.write('layout: word-index\n')
        index_file.write('query_type: {}\n'.format(query_type))
        index_file.write('word: {}\n'.format(word))
        index_file.write('title: {}\n'.format(word))
        index_file.write('permalink: /:collection/:path\n')
        index_file.write('---\n')
    for house in HOUSES:
        house_dir = os.path.join(results_dir, house)
        if not os.path.exists(house_dir):
            os.makedirs(house_dir)
        with open(os.path.join(house_dir, 'index.html'), 'wb') as index_file:
            index_file.write('---\n')
            index_file.write('layout: word-house-index\n')
            index_file.write('word: {}\n'.format(word))
            index_file.write('title: {} - {}\n'.format(word, house))
            index_file.write('house: {}\n'.format(house))
            index_file.write('permalink: /:collection/:path\n')
            index_file.write('---\n')
        decade_dir = os.path.join(house_dir, decade)
        speakers = defaultdict(int)
        topics = defaultdict(int)
        days = defaultdict(int)
        texts = ''
        sentences = []
        total_words = 0
        dbclient = MongoClient(MONGO_URL)
        db = dbclient.get_default_database()
        total_speeches = db.speeches.find({'house': house, 'decade': decade}).count()
        # db.speeches.create_index([('text', TEXT)])
        # Number of speeches containing word
        results = db.speeches.find({'house': house, 'decade': decade, 'words.w': word})
        total = results.count()
        # Graph over time?
        # Assemble as corpus
        if results:
            if not os.path.exists(decade_dir):
                os.makedirs(decade_dir)
            # Make index page
            for result in results:
                freq = (w for w in result['words'] if w['w'] == word).next()
                total_words += freq['c']
                url = 'https://historichansard.net/{}/{}/{}/'.format(house, result['year'], result['filename'])
                if 'subdebate_title' in result:
                    title = '{}: {}'.format(result['debate_title'].encode('utf-8'), result['subdebate_title'].encode('utf-8'))
                    speech_url = '{}#subdebate-{}-{}'.format(url, result['debate_index'], result['subdebate_index'])
                else:
                    title = result['debate_title'].encode('utf-8')
                    speech_url = '{}#debate-{}'.format(url, result['debate_index'])
                try:
                    topics[title] += freq['c']
                except KeyError:
                    topics[title] = freq['c']
                try:
                    speakers[result['speaker']['id']] += freq['c']
                except KeyError:
                    speakers[result['speaker']['id']] = freq['c']
                try:
                    days[result['date']]['count'] += freq['c']
                except (KeyError, TypeError):
                    days[result['date']] = {'url': url, 'count': freq['c'], 'date': result['date']}
                for para in result['text']:
                    if re.search(r'\b{}\b'.format(word), para, flags=re.IGNORECASE):
                        texts += '{}\n'.format(para.encode('utf-8'))
                        para_blob = TextBlob(para.encode('ascii', errors="ignore"))
                        for sentence in para_blob.sentences:
                            if word in str(sentence).lower():
                                sentences.append({'url': speech_url, 'sentence': sentence})
            blob = TextBlob(texts.decode('ascii', errors="ignore"))
            # total_words = blob.words.count(word)
            sorted_speakers = sorted(speakers, key=speakers.get, reverse=True)
            sorted_days = sorted(days.values(), key=itemgetter('count'), reverse=True)
            sorted_topics = sorted(topics, key=topics.get, reverse=True)
            day_x = []
            day_y = []
            for day in sorted_days:
                day_x.append(datetime.strptime(day['date'], '%Y-%m-%d'))
                day_y.append(day['count'])
            layout = go.Layout(
                xaxis=dict(
                    title='Date'
                ),
                yaxis=dict(
                    title='Number of mentions'
                )
                # width=1000,
                # height=500
            )
            data = [go.Bar(x=day_x, y=day_y)]
            figure = go.Figure(data=data, layout=layout)
            plotly_url = py.plot(figure, filename='{}-{}-{}-bar'.format(word, house, decade), auto_open=False)
            plot_id = re.search(r'(\d+)', plotly_url).group(1)
            # fig = py.get_figure('wragge', plot_id)
            # py.image.save_as(fig, filename='{}/{}-{}-{}.png'.format(decade_dir, word, house, decade))
            bubbleline_url = create_bubblelines([word], house, decade)
            bubble_id = re.search(r'(\d+)', bubbleline_url).group(1)
            if len(word.split()) == 1:
                blob = TextBlob(texts.decode('ascii', errors="ignore"))
                finder = BigramCollocationFinder.from_words(blob.words.lower())
                finder.apply_freq_filter(3)
                ignored_words = nltk.corpus.stopwords.words('english')
                finder.apply_word_filter(lambda w: len(w) < 3 or w.lower() in ignored_words)
                finder.apply_ngram_filter(lambda *w: word not in w)
                # collocations = finder.nbest(nltk.collocations.BigramAssocMeasures().likelihood_ratio, 100)
                collocations = sorted(finder.ngram_fd.items(), key=lambda t: (-t[1], t[0]))[:100]
            else:
                collocations = []
            # for sentence in blob.sentences:
            #    if word in str(sentence).lower():
            #        sentences.append(sentence)
            output = '---\n'
            output += 'layout: default\n'
            output += 'word: "{}"\n'.format(word)
            output += 'query_type: "{}"\n'.format(query_type)
            output += 'house: "{}"\n'.format(house)
            output += 'house_full: "{}"\n'.format(HOUSE_NAMES[house])
            output += 'decade: "{}"\n'.format(decade)
            output += 'title: "{} - {} - {}"\n'.format(word, house, decade)
            output += 'permalink: /:collection/:path\n'
            output += 'bubble_id: {}\n'.format(bubble_id)
            output += 'total_words: {}\n'.format(total_words)
            output += 'total_speeches: {}\n'.format(total)
            output += '---\n\n'
            output += '\n## Searching for the {} **{}** in {} within the {}s...\n\n'.format(query_type, word, HOUSE_NAMES[house], decade)
            output += '<iframe width="100%" height="400" frameborder="0" scrolling="no" src="//plot.ly/~wragge/{}.embed"></iframe>\n\n'.format(bubble_id)
            output += '### The {} **{}**\n\n'.format(query_type, word)
            output += '* appears in {:.1%} of speeches\n'.format(float(total) / total_speeches)
            output += '* appears {} times in {} speeches\n'.format(total_words, total)
            output += '* was spoken on {} sitting days by {} different people\n'.format(len(days), len(speakers))
            output += '* appears in speeches on {} different topics\n'.format(len(topics))
            output += '\n### Top speakers:\n\n'
            for speaker in sorted_speakers[:5]:
                details = db.people.find_one({'_id': speaker})
                try:
                    speaker_name = [n for n in details['display_names'] if 'SPEAKER' not in n and 'CHAIRMAN' not in n][0]
                except TypeError:
                    speaker_name = details['names'][0]
                output += '* {} ({} uses)\n'.format(speaker_name, speakers[speaker])
            output += '* [View all...](speakers/)\n'
            output += '\n\n### Top days:\n\n'
            for day in sorted_days[:5]:
                formatted_date = datetime.strptime(day['date'], '%Y-%m-%d').strftime('%-d %B %Y')
                output += '* {} ({} uses)\n'.format(formatted_date, day['count'])
            output += '* [View all...](days/)\n'
            output += '\n\n### Top topics:\n\n'
            for topic in sorted_topics[:5]:
                output += '* {} ({} uses)\n'.format(topic, topics[topic])
            output += '* [View all...](topics/)\n'
            if collocations:
                output += '\n\n### Associated words:\n\n'
                for collocation in collocations[:5]:
                    output += '* {} ({} appearances)\n'.format(' '.join(collocation[0]), collocation[1])
                output += '* [View all...](collocations/)\n'
            output += '\n\n### Sample sentences:\n\n'
            try:
                sample_sentences = random.sample(sentences, 5) if len(sentences) else sentences
            except ValueError:
                sample_sentences = sentences
            for sentence in sample_sentences:
                output += '* {}\n\n'.format(re.sub(r'\b({})\b'.format(word), r'<span class="highlight">\1</span>', str(sentence['sentence']), flags=re.IGNORECASE))
            output += '* [View all...](contexts/)\n'
            print output
            with open(os.path.join(decade_dir, 'index.md'), 'wb') as md_file:
                md_file.write(output)
            with open(os.path.join(decade_dir, 'speakers.md'), 'wb') as md_file:
                md_file.write('---\n')
                md_file.write('layout: default\n')
                md_file.write('title: {} - {} - {} - Speakers\n'.format(word, house, decade))
                md_file.write('---\n')
                md_file.write('## Speakers who used the {} **{}** in the {} during the {}s\n\n'.format(query_type, word, HOUSE_NAMES[house], decade))
                md_file.write('| Speaker name | Number of uses |\n')
                md_file.write('|--------------|----------------|\n')
                for speaker in sorted_speakers:
                    details = db.people.find_one({'_id': speaker})
                    try:
                        speaker_name = [n for n in details['display_names'] if 'SPEAKER' not in n and 'CHAIRMAN' not in n][0]
                    except (TypeError, IndexError):
                        speaker_name = details['names'][0]
                    md_file.write('|{}|{}|\n'.format(speaker_name, speakers[speaker]))
            with open(os.path.join(decade_dir, 'days.md'), 'wb') as md_file:
                md_file.write('---\n')
                md_file.write('layout: default\n')
                md_file.write('title: {} - {} - {} - Days\n'.format(word, house, decade))
                md_file.write('---\n')
                md_file.write('## Sitting days when the {} **{}** was used in the {} during the {}s\n\n'.format(query_type, word, HOUSE_NAMES[house], decade))
                # md_file.write('[![Chart of frequencies by date](../{}-{}-{}.png)]({})\n\n'.format(word, house, decade, plotly_url))
                md_file.write('<iframe width="100%" height="400" frameborder="0" scrolling="no" src="//plot.ly/~wragge/{}.embed"></iframe>\n\n'.format(plot_id))
                md_file.write('| Date | Number of uses |\n')
                md_file.write('|--------------|----------------|\n')
                for day in sorted_days:
                    formatted_date = datetime.strptime(day['date'], '%Y-%m-%d').strftime('%-d %B %Y')
                    md_file.write('|[{}]({})|{}|\n'.format(formatted_date, day['url'], day['count']))
            with open(os.path.join(decade_dir, 'topics.md'), 'wb') as md_file:
                md_file.write('---\n')
                md_file.write('layout: default\n')
                md_file.write('title: {} - {} - {} - Topics\n'.format(word, house, decade))
                md_file.write('---\n')
                md_file.write('## Topics when the {} **{}** was used in the {} during the {}s\n\n'.format(query_type, word, HOUSE_NAMES[house], decade))
                md_file.write('| Topic | Number of uses |\n')
                md_file.write('|--------------|----------------|\n')
                for topic in sorted_topics:
                    md_file.write('|{}|{}|\n'.format(topic, topics[topic]))
            if collocations:
                with open(os.path.join(decade_dir, 'collocations.md'), 'wb') as md_file:
                    md_file.write('---\n')
                    md_file.write('layout: default\n')
                    md_file.write('title: {} - {} - {} - Collocations\n'.format(word, house, decade))
                    md_file.write('---\n')
                    md_file.write('## Collocations for the {} **{}** when used in the {} during the {}s\n\n'.format(query_type, word, HOUSE_NAMES[house], decade))
                    md_file.write('| Collocation | Frequency |\n')
                    md_file.write('|--------------|----------------|\n')
                    for collocation in collocations:
                        md_file.write('|{}|{}|\n'.format(' '.join(collocation[0]), collocation[1]))
            with open(os.path.join(decade_dir, 'contexts.md'), 'wb') as md_file:
                md_file.write('---\n')
                md_file.write('layout: default\n')
                md_file.write('title: {} - {} - {} - Contexts\n'.format(word, house, decade))
                md_file.write('---\n')
                md_file.write('## Contexts in which the {} **{}** was used in the {} during the {}s\n\n'.format(query_type, word, HOUSE_NAMES[house], decade))
                for sentence in sentences:
                    md_file.write('* {} [[More&hellip;]]({})\n\n'.format(re.sub(r'\b({})\b'.format(word), r'<span class="highlight">\1</span>', str(sentence['sentence']), flags=re.IGNORECASE), sentence['url']))
            # Contexts -- sentences
            # People
            # Debates
            # Collocations


def comparisons(words, decade):
    plot_ids = {}
    for house in HOUSES:
        plotly_url = create_bubblelines(words, house, decade)
        plot_ids[house] = re.search(r'(\d+)', plotly_url).group(1)
    for word in words:
        print word
        word_dir = os.path.join('docs', '_words', word.replace(' ', '-').strip('"'))
        if not os.path.exists(word_dir):
            word_summary(word, decade)
    with open(os.path.join('docs', '_comparisons', '{}.md'.format(' '.join(words).replace(' ', '-'))), 'wb') as md_file:
        md_file.write('---\n')
        md_file.write('layout: comparison\n')
        md_file.write('decade: {}\n'.format(decade))
        md_file.write('words:\n')
        for word in words:
            md_file.write('    - {}\n'.format(word))
        md_file.write('hofreps_plot: {}\n'.format(plot_ids['hofreps']))
        md_file.write('senate_plot: {}\n'.format(plot_ids['senate']))
        md_file.write('---\n')


def make_clouds():
    for house in HOUSES:
        # results = generate_tfidf(os.path.join('data', 'speeches', 'decades', house), 1)
        results = generate_tfidf(os.path.join('data', 'speeches', 'parliaments', house), 1)
        for result in results:
            # image_name = os.path.join('data', 'images', '{}-decade-{}.png'.format(result['name'], house))
            image_name = os.path.join('data', 'images', '{}-parliament-{}.png'.format(result['name'], house))
            wordcloud = WordCloud(width=1200, height=800).fit_words(result['scores'])
            image = wordcloud.to_image()
            image.save(image_name)


def create_bubblelines(words, house, decade):
    traces = []
    for word in words:
        dates = []
        counts = []
        labels = []
        text = []
        results = word_frequency(word, house, decade)
        for result in results:
            dates.append(result['date'])
            counts.append(result['count'] * 10)
            text.append('{} uses'.format(result['count']))
            labels.append(word)
        trace = dict(
            type='scatter',
            x=dates,
            y=labels,
            text=text,
            mode='markers',
            marker=dict(
                size=counts,
                opacity=0.4,
                sizemode="area"
            ),
            hoverinfo='x+text'
        )
        traces.append(trace)
    layout = go.Layout(
        title='Word frequencies: {}, {}s'.format(HOUSE_NAMES[house], decade),
        xaxis=dict(
            title='Date'
        ),
        yaxis=dict(
            tickfont=dict(
                size=14
            )
        ),
        margin=dict(
            l=120,
            r=80,
            t=100,
            b=100
        ),
        showlegend=False
    )
    figure = dict(data=traces, layout=layout)
    plotly_url = py.plot(figure, filename='{}-{}-{}-bubbles'.format('-'.join(words), house, decade), validate=False, auto_open=False)
    return plotly_url


def people(decade):
    dbclient = MongoClient(MONGO_URL)
    db = dbclient.get_default_database()
    all_friends = compare_people()
    tfidf = generate_tfidf(os.path.join('data', 'speeches', 'people'), 1)
    people = [p for p in list_people(decade='1970') if p['_id'] not in ['20000', '10000']]
    for person in people:
        friends = all_friends[person['_id']]
        person_dir = os.path.join('docs', '_people', '{}-{}'.format(person['_id'], friends['name'].lower().replace(',', '').replace(' ', '-')))
        if not os.path.exists(person_dir):
            os.makedirs(person_dir)
            print person['_id']
            topics = defaultdict(int)
            days = defaultdict(int)
            total_speeches = db.speeches.count({'speaker.id': person['_id'], 'decade': decade})
            speeches = db.speeches.find({'speaker.id': person['_id'], 'decade': decade})
            for result in speeches:
                texts = ''
                url = 'https://historichansard.net/{}/{}/{}/'.format(result['house'], result['year'], result['filename'])
                if 'subdebate_title' in result:
                    title = '{}: {}'.format(result['debate_title'].encode('utf-8'), result['subdebate_title'].encode('utf-8'))
                    speech_url = '{}#subdebate-{}-{}'.format(url, result['debate_index'], result['subdebate_index'])
                else:
                    title = result['debate_title'].encode('utf-8')
                    speech_url = '{}#debate-{}'.format(url, result['debate_index'])
                try:
                    topics[title] += 1
                except KeyError:
                    topics[title] = 1
                for para in result['text']:
                    texts += '{}\n'.format(para.encode('utf-8'))
                speech_blob = TextBlob(texts.decode('ascii', errors="ignore"))
                try:
                    days[result['date']]['count'] += len(speech_blob.words())
                except (KeyError, TypeError):
                    days[result['date']] = {'url': url, 'count': len(speech_blob.words), 'date': result['date']}
                data_dir = os.path.join('data', 'speeches', 'people')
                for file in os.listdir(data_dir):
                    if file.split('-')[0] == person['_id']:
                        data_file = file
                        break
            with open(os.path.join(data_dir, data_file), 'rb') as text_file:
                blob = TextBlob(text_file.read().decode('ascii', errors="ignore"))
            total_words = len(blob.words)
            for score in tfidf:
                if score['name'] == data_file[:-4]:
                    sig_words = score['scores']
                    break
            sorted_days = sorted(days.values(), key=itemgetter('count'), reverse=True)
            sorted_topics = sorted(topics, key=topics.get, reverse=True)
            word_counts = [[word, count] for word, count in blob.lower().word_counts.items() if word not in STOPWORDS and count > 1]
            bigrams = [' '.join(bigram).lower() for bigram in blob.lower().ngrams(2) if stopwords_check(bigram)]
            bigram_counts = [[word, count] for word, count in Counter(bigrams).items() if count > 1]
            trigrams = [' '.join(trigram).lower() for trigram in blob.lower().ngrams(3) if stopwords_check(trigram)]
            trigram_counts = [[word, count] for word, count in Counter(trigrams).items() if count > 1]
            word_counts = sorted(word_counts, key=itemgetter(1), reverse=True)[:200]
            bigram_counts = sorted(bigram_counts, key=itemgetter(1), reverse=True)[:200]
            trigram_counts = sorted(trigram_counts, key=itemgetter(1), reverse=True)[:200]
            # np_counts = [[word, count] for word, count in blob.lower().np_counts.items() if count > 1]
            # np_counts = sorted(np_counts, key=itemgetter(1), reverse=True)[:200]
            day_x = []
            day_y = []
            for day in sorted_days:
                day_x.append(datetime.strptime(day['date'], '%Y-%m-%d'))
                day_y.append(day['count'])
            layout = go.Layout(
                xaxis=dict(
                    title='Date'
                ),
                yaxis=dict(
                    title='Number of words'
                )
                # width=1000,
                # height=500
            )
            data = [go.Bar(x=day_x, y=day_y)]
            figure = go.Figure(data=data, layout=layout)
            plotly_url = py.plot(figure, filename='{}-{}-bar'.format(person['_id'], decade), auto_open=False)
            plot_id = re.search(r'(\d+)', plotly_url).group(1)
            with open(os.path.join(person_dir, 'index.md'), 'wb') as person_file:
                person_file.write('---\n')
                person_file.write('layout: default\n')
                person_file.write('title: {}\n'.format(friends['name']))
                person_file.write('person_party: {}\n'.format(friends['party']))
                person_file.write('plot_id: {}\n'.format(plot_id))
                person_file.write('total_words: {}\n'.format(total_words))
                person_file.write('permalink: /:collection/:path\n')
                person_file.write('---\n\n')
                person_file.write('## {}\n'.format(friends['name']))
                person_file.write('\n<iframe width="100%" height="400" frameborder="0" scrolling="no" src="//plot.ly/~wragge/{}.embed"></iframe>\n\n'.format(plot_id))
                person_file.write('\n### Summary for the {}s:\n\n'.format(decade))
                person_file.write('* {} words spoken\n'.format(total_words))
                person_file.write('* {} speeches over {} sitting days\n'.format(total_speeches, len(days)))
                person_file.write('\n\n### Top days:\n\n')
                for day in sorted_days[:5]:
                    formatted_date = datetime.strptime(day['date'], '%Y-%m-%d').strftime('%-d %B %Y')
                    person_file.write('* {} ({} words)\n'.format(formatted_date, day['count']))
                person_file.write('* [View all...](days/)\n')
                person_file.write('\n\n### Top topics:\n\n')
                for topic in sorted_topics[:5]:
                    person_file.write('* {} ({} speeches)\n'.format(topic, topics[topic]))
                person_file.write('* [View all...](topics/)\n')
                person_file.write('\n\n### Top words:\n\n')
                for word in word_counts[:5]:
                    person_file.write('* {} ({} uses)\n'.format(word[0].encode('utf-8'), word[1]))
                person_file.write('* [View all...](words/)\n')
                person_file.write('\n\n### Distinctive words:\n\n')
                for word, score in sig_words[:5]:
                    person_file.write('* {} ({})\n'.format(word.encode('utf-8'), score))
                person_file.write('* [View all...](sig_words/)\n')
                if bigram_counts:
                    person_file.write('\n\n### Top bigrams:\n\n')
                    for word in bigram_counts[:5]:
                        person_file.write('* {} ({} uses)\n'.format(word[0].encode('utf-8'), word[1]))
                    person_file.write('* [View all...](bigrams/)\n')
                if trigram_counts:
                    person_file.write('\n\n### Top trigrams:\n\n')
                    for word in trigram_counts[:5]:
                        person_file.write('* {} ({} uses)\n'.format(word[0].encode('utf-8'), word[1]))
                    person_file.write('* [View all...](trigrams/)\n')
                '''
                if np_counts:
                    person_file.write('\n\n### Top noun phrases:\n\n')
                    for word in np_counts[:5]:
                        person_file.write('* {} ({} uses)\n'.format(word[0], word[1]))
                    person_file.write('* [View all...](noun_phrases/)\n')
                '''
                person_file.write('\n\n### Most like:\n\n')
                for friend in friends['friends'][:5]:
                    person_file.write('* {} {}\n'.format(friend['name'], '({})'.format(friend['party']) if friend['party'] else ''))
                person_file.write('* [View all...](similarities/)\n')
            with open(os.path.join(person_dir, 'days.md'), 'wb') as md_file:
                md_file.write('---\n')
                md_file.write('layout: default\n')
                md_file.write('title: {} - {} - Days\n'.format(person['_id'], friends['name'].lower().replace(',', '').replace(' ', '-')))
                md_file.write('---\n')
                md_file.write('## Sitting days when {} spoke during the {}s\n\n'.format(friends['name'], decade))
                # md_file.write('[![Chart of frequencies by date](../{}-{}-{}.png)]({})\n\n'.format(word, house, decade, plotly_url))
                md_file.write('<iframe width="100%" height="400" frameborder="0" scrolling="no" src="//plot.ly/~wragge/{}.embed"></iframe>\n\n'.format(plot_id))
                md_file.write('| Date | Number of words |\n')
                md_file.write('|--------------|----------------|\n')
                for day in sorted_days:
                    formatted_date = datetime.strptime(day['date'], '%Y-%m-%d').strftime('%-d %B %Y')
                    md_file.write('|[{}]({})|{}|\n'.format(formatted_date, day['url'], day['count']))
            with open(os.path.join(person_dir, 'topics.md'), 'wb') as md_file:
                md_file.write('---\n')
                md_file.write('layout: default\n')
                md_file.write('title: {} - {} - Topics\n'.format(person['_id'], friends['name'].lower().replace(',', '').replace(' ', '-')))
                md_file.write('---\n')
                md_file.write('## Topics that {} spoke about during the {}s\n\n'.format(friends['name'], decade))
                md_file.write('| Topic | Number of speeches |\n')
                md_file.write('|--------------|----------------|\n')
                for topic in sorted_topics:
                    md_file.write('|{}|{}|\n'.format(topic, topics[topic]))
            with open(os.path.join(person_dir, 'words.md'), 'wb') as md_file:
                md_file.write('---\n')
                md_file.write('layout: default\n')
                md_file.write('title: {} - {} - Words\n'.format(person['_id'], friends['name'].lower().replace(',', '').replace(' ', '-')))
                md_file.write('---\n')
                md_file.write('## Words used by {} during the {}s\n\n'.format(friends['name'], decade))
                md_file.write('| Words | Number of uses |\n')
                md_file.write('|--------------|----------------|\n')
                for word in word_counts:
                    md_file.write('|{}|{}|\n'.format(word[0], word[1]))
            with open(os.path.join(person_dir, 'sig_words.md'), 'wb') as md_file:
                md_file.write('---\n')
                md_file.write('layout: default\n')
                md_file.write('title: {} - {} - Distinctive words\n'.format(person['_id'], friends['name'].lower().replace(',', '').replace(' ', '-')))
                md_file.write('---\n')
                md_file.write('## Distinctive words used by {} during the {}s\n\n'.format(friends['name'], decade))
                md_file.write('| Words | TF-IDF score |\n')
                md_file.write('|--------------|----------------|\n')
                for word in sig_words:
                    md_file.write('|{}|{}|\n'.format(word[0].encode('utf-8'), word[1]))
            if bigram_counts:
                with open(os.path.join(person_dir, 'bigrams.md'), 'wb') as md_file:
                    md_file.write('---\n')
                    md_file.write('layout: default\n')
                    md_file.write('title: {} - {} - Bigrams\n'.format(person['_id'], friends['name'].lower().replace(',', '').replace(' ', '-')))
                    md_file.write('---\n')
                    md_file.write('## Words used by {} during the {}s\n\n'.format(friends['name'], decade))
                    md_file.write('| Bigrams | Number of uses |\n')
                    md_file.write('|--------------|----------------|\n')
                    for word in bigram_counts:
                        md_file.write('|{}|{}|\n'.format(word[0].encode('utf-8'), word[1]))
            if trigram_counts:
                with open(os.path.join(person_dir, 'trigrams.md'), 'wb') as md_file:
                    md_file.write('---\n')
                    md_file.write('layout: default\n')
                    md_file.write('title: {} - {} - Trigrams\n'.format(person['_id'], friends['name'].lower().replace(',', '').replace(' ', '-')))
                    md_file.write('---\n')
                    md_file.write('## Words used by {} during the {}s\n\n'.format(friends['name'], decade))
                    md_file.write('| Trigrams | Number of uses |\n')
                    md_file.write('|--------------|----------------|\n')
                    for word in trigram_counts:
                        md_file.write('|{}|{}|\n'.format(word[0].encode('utf-8'), word[1]))
            '''
            if np_counts:
                with open(os.path.join(person_dir, 'noun_phrases.md'), 'wb') as md_file:
                    md_file.write('---\n')
                    md_file.write('layout: default\n')
                    md_file.write('title: {} - {} - Noun Phrases\n'.format(person['_id'], friends['name'].lower().replace(',', '').replace(' ', '-')))
                    md_file.write('---\n')
                    md_file.write('## Words used by {} during the {}s\n\n'.format(friends['name'], decade))
                    md_file.write('| Noun phrases | Number of uses |\n')
                    md_file.write('|--------------|----------------|\n')
                    for word in np_counts:
                        md_file.write('|{}|{}|\n'.format(word[0], word[1]))
            '''
            with open(os.path.join(person_dir, 'similarities.md'), 'wb') as md_file:
                md_file.write('---\n')
                md_file.write('layout: default\n')
                md_file.write('title: {} - {} - Like speakers\n'.format(person['_id'], friends['name'].lower().replace(',', '').replace(' ', '-')))
                md_file.write('---\n')
                md_file.write('## People whose speech is most like {} during the {}s\n\n'.format(friends['name'], decade))
                md_file.write('| Name | Party | Similarity|\n')
                md_file.write('|--------------|----------------|----------------|\n')
                for friend in friends['friends']:
                    md_file.write('|{}|{}|{}|\n'.format(friend['name'], friend['party'], friend['score']))


def compare_people(data_dir='data/speeches/people/'):
    dbclient = MongoClient(MONGO_URL)
    db = dbclient.get_default_database()
    data = {}
    people = []
    names = [file[:-4] for file in os.listdir(data_dir) if file[-4:] == '.txt']
    for name in names:
        p_id = name.split('-')[0]
        person = db.people.find_one({'_id': p_id})
        people.append(person)
    # Get a list of filenames to feed to scikit-learn
    files = [os.path.join(data_dir, file) for file in os.listdir(data_dir) if file[-4:] == '.txt']
    tfidf = TfidfVectorizer(input='filename').fit_transform(files)
    results = (tfidf * tfidf.T).A
    for index, row in enumerate(results):
        try:
            title_name = [n for n in people[index]['display_names'] if 'SPEAKER' not in n and 'CHAIRMAN' not in n][0]
        except TypeError:
            title_name = people[index]['names'][0]
        try:
            title_party = people[index]['parties'][0].split(';')[0]
        except (KeyError, IndexError, TypeError, AttributeError):
            title_party = None
        # print '\n\n{} {}\n'.format(title_name, '({})'.format(title_party) if title_party else '')
        data[people[index]['_id']] = {'name': title_name, 'party': title_party, 'friends': []}
        scores = [pair for pair in zip(range(0, len(row)), row)]
        sorted_scores = sorted(scores, key=lambda t: t[1] * -1)
        friends = sorted_scores[1:]
        for friend in friends:
            try:
                friend_name = [n for n in people[friend[0]]['display_names'] if 'SPEAKER' not in n and 'CHAIRMAN' not in n][0]
            except TypeError:
                friend_name = people[friend[0]]['names'][0]
            try:
                friend_party = people[friend[0]]['parties'][0].split(';')[0]
            except (KeyError, IndexError, TypeError, AttributeError):
                friend_party = None
            # print '    * {:40} {}'.format('{} ({})'.format(friend_name, friend_party) if friend_party else friend_name, friend[1])
            data[people[index]['_id']]['friends'].append({'name': friend_name, 'party': friend_party, 'score': friend[1]})
    return data


def compare_years(data_dir='data/speeches/years/'):
    for house in HOUSES:
        names = [file[:-4] for file in os.listdir(os.path.join(data_dir, house)) if file[-4:] == '.txt']
        files = [os.path.join(data_dir, house, file) for file in os.listdir(os.path.join(data_dir, house)) if file[-4:] == '.txt']
        tfidf = TfidfVectorizer(input='filename').fit_transform(files)
        results = (tfidf * tfidf.T).A
        for index, row in enumerate(results):
            print '\n\n{}\n'.format(names[index])
            scores = [pair for pair in zip(range(0, len(row)), row)]
            sorted_scores = sorted(scores, key=lambda t: t[1] * -1)
            labelled_scores = [(names[id], score) for (id, score) in sorted_scores[1:]]
            for score in labelled_scores[:10]:
                print '    * {:40} {}'.format(score[0], score[1])
            # data[people[index]['_id']]['friends'].append({'name': friend_name, 'party': friend_party, 'score': friend[1]})
    # return data


def search_speeches(keywords, start_year=None, house=None):
    dbclient = MongoClient(MONGO_URL)
    db = dbclient.get_default_database()
    query = {}
    filename = keywords.strip('\"').replace(' ', '-')
    if house:
        query['house'] = house
        filename += '-{}'.format(house)
    if start_year:
        query['year'] = {'$gte': start_year}
        filename += '-{}'.format(start_year)
    query['$text'] = {'$search': keywords}
    pipeline = [
        {'$match': query},
        {'$group': {'_id': '$date', 'debates': {'$addToSet': '$debate_index'}, 'count': {'$sum': 1}}},
        {'$project': {'_id': 0, 'date': '$_id', 'debates': 1, 'count': 1}},
        {'$sort': {'date': 1}}
    ]
    results = list(db.speeches.aggregate(pipeline))
    with open(os.path.join('data', 'searches', '{}.csv'.format(filename)), 'wb') as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(['date', 'debate', 'speaker', 'speaker_id', 'context', 'speech_url'])
        for result in results:
            print '{}: {}'.format(result['date'], result['count'])
            if house:
                query['house'] = house
            query['date'] = result['date']
            query['$text'] = {'$search': keywords}
            speeches = db.speeches.find(query).sort([('debate_index', 1), ('speech_index', 1)])
            for speech in speeches:
                context = ''
                url = 'https://historichansard.net/{}/{}/{}/'.format(speech['house'], speech['year'], speech['filename'])
                if 'subdebate_title' in speech:
                    title = '{}: {}'.format(speech['debate_title'].encode('utf-8'), speech['subdebate_title'].encode('utf-8'))
                    speech_url = '{}#subdebate-{}-{}'.format(url, speech['debate_index'], speech['subdebate_index'])
                else:
                    title = speech['debate_title'].encode('utf-8')
                    speech_url = '{}#debate-{}'.format(url, speech['debate_index'])
                print '{}:'.format(speech['speaker']['name'])
                for para in speech['text']:
                    blob = TextBlob(para)
                    for sentence in blob.sentences:
                        if keywords.strip('\"').lower() in str(sentence).lower():
                            context = sentence
                            break
                print '{}\n'.format(context)
                writer.writerow([speech['date'], title, speech['speaker']['name'], speech['speaker']['id'], context, speech_url])


