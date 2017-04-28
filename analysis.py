from bs4 import BeautifulSoup
import bs4
import os
import re
import pprint
import time
from datetime import datetime
from pymongo import MongoClient, TEXT
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

from credentials import MONGO_URL

XML_DIR = os.path.join(os.path.dirname(__file__), 'xml')
PARLIAMENTS = [str(p) for p in range(1, 33)]
HOUSES = ['hofreps', 'senate']
YEARS = [str(y) for y in range(1901, 1981)]
STOPWORDS = nltk.corpus.stopwords.words('english')


WORDs = [
    'community',
    'individualism',
    'revolution',
    'modernisation',
    'crisis',
    #'white australia',
    'immigration',
    'multiculturalism',
    'britishness',
    'aborigines',
    'freedoms',
    'welfare',
    'tyranny',
    #'social experiment',
    'federation',
    'states',
    'alliance',
    'independence',
    'decolonisation',
    #'arms race',
    #'papua new guinea'
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


def list_people(house, decade=None, parliament=None, party=None):
    dbclient = MongoClient(MONGO_URL)
    db = dbclient.get_default_database()
    query = {'house': house}
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
    db.people.insert_many(people)


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


def write_speeches_by_person(house, decade=None, parliament=None):
    dbclient = MongoClient(MONGO_URL)
    db = dbclient.get_default_database()
    query = {'house': house}
    if decade:
        query['decade'] = decade
    if parliament:
        query['parliament'] = parliament
    pipeline = [
        {'$match': query},
        {'$group': {'_id': '$speaker.id', 'names': {'$addToSet': "$speaker.display_name"}}}
    ]
    people = db.speeches.aggregate(pipeline)
    for person in people:
        person_name = person['names'][0]
        for name in person['names']:
            if not re.search(r'SPEAKER|CHAIRMAN', name):
                person_name = name
                break
        try:
            filename = '{}-{}.txt'.format(person['_id'], person_name.lower().replace(', ', '-').replace(' ', '-'))
        except UnicodeEncodeError:
            filename = '{}-{}.txt'.format(person['_id'], "".join(i for i in person_name.lower().replace(' ', '-').replace('.', '-') if ord(i) < 128))
        with open(os.path.join('data', 'speeches', 'people', filename), 'ab') as text_file:
            speeches = db.speeches.find({'speaker.id': person['_id']}).sort('date')
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


def word_summary(word, house, decade):
    results_dir = os.path.join('data', 'words', '{}-{}-{}'.format(word.replace(' ', '-').strip('"'), house, decade))
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
        if not os.path.exists(results_dir):
            os.makedirs(results_dir)
        for result in results:
            freq = (w for w in result['words'] if w['w'] == word).next()
            total_words += freq['c']
            if 'subdebate_title' in result:
                title = '{}: {}'.format(result['debate_title'].encode('utf-8'), result['subdebate_title'].encode('utf-8'))
                url = 'https://historichansard.net/{}/{}/{}/#subdebate-{}-{}'.format(house, result['year'], result['filename'], result['debate_index'], result['subdebate_index'])
            else:
                title = result['debate_title'].encode('utf-8')
                url = 'https://historichansard.net/{}/{}/{}/#debate-{}'.format(house, result['year'], result['filename'], result['debate_index'])
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
            except KeyError:
                days[result['date']] = {'url': url, 'count': freq['c']}
            for para in result['text']:
                if re.search(r'\b{}\b'.format(word), para, flags=re.IGNORECASE):
                    texts += '{}\n'.format(para.encode('utf-8'))
                    para_blob = TextBlob(para.decode('ascii', errors="ignore"))
                    for sentence in para_blob.sentences:
                        if word in str(sentence).lower():
                            sentences.append({'url': url, 'sentence': sentence})
        blob = TextBlob(texts.decode('ascii', errors="ignore"))
        # total_words = blob.words.count(word)
        day_x = []
        day_y = []
        for day in sorted(days):
            day_x.append(datetime.strptime(day, '%Y-%m-%d'))
            day_y.append(days[day])
        layout = go.Layout(
            xaxis=dict(
                title='Date'
            ),
            yaxis=dict(
                title='Number of mentions'
            ),
            width=1000,
            height=500
        )
        data = [go.Bar(x=day_x, y=day_y)]
        figure = go.Figure(data=data, layout=layout)
        plotly_url = py.plot(figure, filename='{}-{}-{}'.format(word, house, decade))
        plot_id = re.search(r'(\d+)', plotly_url).group(1)
        fig = py.get_figure('wragge', plot_id)
        py.image.save_as(fig, filename='{}/{}-{}-{}.png'.format(results_dir, word, house, decade))
        sorted_speakers = sorted(speakers, key=speakers.get, reverse=True)
        sorted_days = sorted(days, key=itemgetter('count'), reverse=True)
        sorted_topics = sorted(topics, key=topics.get, reverse=True)
        if len(word.split() == 1):
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
        output = '\n## Searching for "{}" in {} within the {}s...\n\n'.format(word, house, decade)
        output += '----\n\n'
        output += '### The word "{}":\n\n'.format(word)
        output += '* appears in {:.1%} of speeches\n'.format(float(total) / total_speeches)
        output += '* appears {} times in {} speeches\n'.format(total_words, total)
        output += '* was spoken on {} sitting days by {} different people\n'.format(len(days), len(speakers))
        output += '* appears in speeches on {} different topics\n'.format(len(topics))
        output += '\n### Top speakers:\n\n'
        for speaker in sorted_speakers[:5]:
            details = db.people.find_one({'_id': speaker})
            output += '* {} ({} uses)\n'.format(details['display_names'][0], speakers[speaker])
        output += '* [View all...](speakers.md)\n'
        output += '\n\n### Top days:\n\n'
        for day in sorted_days[:5]:
            output += '* {} ({} uses)\n'.format(day, days[day])
        output += '* [View all...](days.md)\n'
        output += '\n\n### Top topics:\n\n'
        for topic in sorted_topics[:5]:
            output += '* {} ({} uses)\n'.format(topic, topics[topic])
        output += '* [View all...](topics.md)\n'
        if collocations:
            output += '\n\n### Associated words:\n\n'
            for collocation in collocations[:5]:
                output += '* {} ({} appearances)\n'.format(' '.join(collocation[0]), collocation[1])
            output += '* [View all...](collocations.md)\n'
        output += '\n\n### Sample sentences:\n\n'
        sample_sentences = random.sample(sentences, 5) if len(sentences) else sentences
        for sentence in sample_sentences:
            output += '* {}\n\n'.format(re.sub(r'\b({})\b'.format(word), r'**\1**', str(sentence), flags=re.IGNORECASE))
        output += '* [View all...](contexts.md)\n'
        print output
        with open(os.path.join(results_dir, 'README.md'), 'wb') as md_file:
            md_file.write(output)
        with open(os.path.join(results_dir, 'speakers.md'), 'wb') as md_file:
            md_file.write('## Speakers who used the word "{}" in the {} during the {}s\n\n'.format(word, house, decade))
            md_file.write('| Speaker name | Number of uses |\n')
            md_file.write('|--------------|----------------|\n')
            for speaker in sorted_speakers:
                details = db.people.find_one({'_id': speaker})
                try:
                    md_file.write('|{}|{}|\n'.format(details['display_names'][0], speakers[speaker]))
                except IndexError:
                    md_file.write('|{}|{}|\n'.format(details['names'][0], speakers[speaker]))
        with open(os.path.join(results_dir, 'days.md'), 'wb') as md_file:
            md_file.write('## Sitting days when the word "{}" was used in the {} during the {}s\n\n'.format(word, house, decade))
            md_file.write('[![Chart of frequencies by date]({}-{}-{}.png)]({})\n\n'.format(word, house, decade, plotly_url))
            md_file.write('| Date | Number of uses |\n')
            md_file.write('|--------------|----------------|\n')
            for day in sorted_days:
                md_file.write('|{}|{}|\n'.format(day, days[day]))
        with open(os.path.join(results_dir, 'topics.md'), 'wb') as md_file:
            md_file.write('## Topics when the word "{}" was used in the {} during the {}s\n\n'.format(word, house, decade))
            md_file.write('| Topic | Number of uses |\n')
            md_file.write('|--------------|----------------|\n')
            for topic in sorted_topics:
                md_file.write('|{}|{}|\n'.format(topic, topics[topic]))
        if collocations:
            with open(os.path.join(results_dir, 'collocations.md'), 'wb') as md_file:
                md_file.write('## Collocations for the word "{}" when used in the {} during the {}s\n\n'.format(word, house, decade))
                md_file.write('| Collocation | Frequency |\n')
                md_file.write('|--------------|----------------|\n')
                for collocation in collocations:
                    md_file.write('|{}|{}|\n'.format(' '.join(collocation[0]), collocation[1]))
        with open(os.path.join(results_dir, 'contexts.md'), 'wb') as md_file:
            md_file.write('## Contexts in which the word "{}" was used in the {} during the {}s\n\n'.format(word, house, decade))
            for sentence in sentences:
                md_file.write('* {}\n\n'.format(re.sub(r'\b({})\b'.format(word), r'**\1**', str(sentence), flags=re.IGNORECASE)))
        # Contexts -- sentences
        # People
        # Debates
        # Collocations


def make_clouds():
    for house in HOUSES:
        results = generate_tfidf(os.path.join('data', 'speeches', 'decades', house), 1)
        for result in results:
            image_name = os.path.join('data', 'images', '{}-decade-{}.png'.format(result['name'], house))
            wordcloud = WordCloud(width=1200, height=800).fit_words(result['scores'])
            image = wordcloud.to_image()
            image.save(image_name)


def chart_frequencies(words, house, decade):
    traces = []
    for word in words:
        dates = []
        counts = []
        labels = []
        text = []
        results = word_frequency(word, house, decade)
        for result in results:
            dates.append(result['date'])
            counts.append(result['count'])
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
                opacity=0.4
            ),
            hoverinfo='x+text'
        )
        traces.append(trace)
    layout = go.Layout(
        title='Word frequencies: {}, {}s'.format(house.upper(), decade),
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
    plotly_url = py.plot(figure, filename='{}-{}-{}'.format('-'.join(words), house, decade), validate=False)
    print plotly_url


def compare_people(data_dir='data/speeches/people/'):
    dbclient = MongoClient(MONGO_URL)
    db = dbclient.get_default_database()
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
        print '\n\n{} {}\n'.format(title_name, '({})'.format(title_party) if title_party else '')
        scores = [pair for pair in zip(range(0, len(row)), row)]
        sorted_scores = sorted(scores, key=lambda t: t[1] * -1)
        friends = sorted_scores[1:11]
        for friend in friends:
            try:
                friend_name = [n for n in people[friend[0]]['display_names'] if 'SPEAKER' not in n and 'CHAIRMAN' not in n][0]
            except TypeError:
                friend_name = people[friend[0]]['names'][0]
            try:
                friend_party = people[friend[0]]['parties'][0].split(';')[0]
            except (KeyError, IndexError, TypeError, AttributeError):
                friend_party = None
            print '    * {:40} {}'.format('{} ({})'.format(friend_name, friend_party) if friend_party else friend_name, friend[1])
