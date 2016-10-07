from flask import Flask, render_template, request, jsonify
from newspaper import Article
import requests
import json
import redis
import os

app = Flask(__name__)

#for development purposes
urls = ['http://www.twincities.com/2016/09/18/chris-coleman-mn-governor/',
        'http://www.startribune.com/minnesota-poll-clinton-keeps-lead-but-trump-gains/393840031/',
        'http://www.mprnews.org/story/2016/09/18/st-cloud-mall-stabbings',
        'http://www.startribune.com/st-cloud-mall-closed-until-monday-is-crime-scene-after-stabbings/393872071/']

#load news source dict from json so it's easy(er) to update
fp = open('./news_sources.json','r')
publications = json.load(fp)
fp.close()

def get_current_gleanings(redis_db):
    gleanings = redis_db.get('gleanings')
    if gleanings:
        gleanings = json.loads(gleanings.decode('utf-8'))
    else:
        gleanings = []

    return gleanings

def update_gleanings(urls, redis_db):
    redis_db.set('gleanings', json.dumps(urls))
    return True

def get_url_from_message(message):
    if '<http' not in message:
        return False

    start = message.find('<http') + 1
    end = message.find('>')
    return message[start:end]

def log_url(url):
    redis_db = redis.from_url(os.environ['REDIS_URL'])

    current_gleanings = get_current_gleanings(redis_db)

    updated = False

    if url not in current_gleanings:
        current_gleanings.append(url)
        update_gleanings(current_gleanings, redis_db)
        print("Added " + url)
        updated = True

    return [updated, len(current_gleanings)]

def parse_tweet(url):
    embed_url = 'https://publish.twitter.com/oembed?url=' + url
    print(embed_url)
    r = requests.get(embed_url)
    tweet_data = r.json()
    html = tweet_data['html'].split("\n")
    tweet = html[0]
    script = html[1]

    return {"type": "tweet",
            "tweet": tweet,
            "script": script}

def parse_article(url):
    article = Article(url)

    publication = "PUBLICATION"
    for pub in publications:
        if pub in url:
            publication = publications[pub]

    article.download()

    parsed = False

    try:
        article.parse()

        parsed = True

        title = article.title

        extracted_authors = article.authors
        authors_singular = False
        authors = 'AUTHORS TK'
        if len(extracted_authors) == 2:
            authors = " and ".join(extracted_authors)
        if len(extracted_authors) > 2:
            authors = ", ".join(extracted_authors[i] for i in range(len(extracted_authors)-1))
            authors += " and " + extracted_authors[-1]
        if len(extracted_authors) == 1:
            authors = extracted_authors[0]
            authors_singular = True

        article_fulltext = article.text
        article_paragraphs = article_fulltext.split("\n\n")
        if len(article_paragraphs) > 4:
            summary = " … ".join(article_paragraphs[0:4])
        else:
            summary = article_fulltext.replace("\n\n"," … ")
    except:
        publication = None
        title = None
        authors = None
        authors_singular = False
        summary = None

    return {
                "type": "article",
                "url": url,
                "parsed": parsed,
                "publication": publication,
                "title": title,
                "authors": authors,
                "authors_singular": authors_singular,
                "summary": summary
            }

@app.route('/build')
def build_glean():

    redis_db = redis.from_url(os.environ['REDIS_URL'])

    url_list = get_current_gleanings(redis_db)

    gleanings = []

    for url in url_list:
        has_tweets = False
        if 'twitter.com/' in url:
            has_tweets = True
            gleanings.append(parse_tweet(url))
        else:
            gleanings.append(parse_article(url))

    return render_template('glean.html', gleanings=gleanings, has_tweets=has_tweets)

@app.route('/add-url', methods=['POST'])
def add_url():
    #todo: store the urls in redis
    message = request.form['text']
    url = get_url_from_message(message)
    result = False
    if url:
        result = log_url(url)
    if result:
        message = {"text": "Story added. {} gleanings on the list so far.".format(result[1])}
    else:
        message = {"text": "Looks like we already have that story."}
    return ""

@app.route('/clear', methods=['GET', 'POST'])
def clear_gleanings():
    message = None
    if request.method == 'POST':
        redis_db = redis.from_url(os.environ['REDIS_URL'])
        redis_db.delete('gleanings')
        message = 'Cleared the gleanings'
    return render_template('clearform.html', message=message)

if __name__ == '__main__':
    app.run()
