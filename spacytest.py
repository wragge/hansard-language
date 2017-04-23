import spacy
import os

DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')


def get_places():
    current_path = os.path.join(DATA_DIR, 'speeches', 'people')
    nlp = spacy.load('en')
    files = [f for f in os.listdir(current_path) if f[-4:] == '.txt']
    for file in files:
        with open(os.path.join(current_path, file), 'rb') as text_file:
            doc = nlp(text_file.read().decode('utf-8'))
            # for word in doc:
            #    print(word.text, word.lemma, word.lemma_, word.tag, word.tag_, word.pos, word.pos_)
            for ent in doc.ents:
                #print ent
                if ent.label_ == 'GPE':
                    print ent.text
