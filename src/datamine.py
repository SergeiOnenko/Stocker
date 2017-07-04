"""
datamine.py
Author: David Wallach

- Uses BeautifulSoup for scraping the data from URLs

This Python module has several purposes oriented around mining data from the web.
The functionality is comprised of gathering urls from google quereis and then getting the data from 
those articles such as the article body and publishing date
"""
import os
import sys
import json
import urllib2, httplib, request
from urlparse import urlparse
import time
import csv
import re
from bs4 import BeautifulSoup
from nltk.tokenize import sent_tokenize, word_tokenize
from datetime import datetime 
import dateutil.parser as dparser



class Node(object):
	"""represents an entry in data.csv that will be used to train our neural network
	"""
	def __init__(self, ticker, domain, url):
		# self.query	= query		#
		self.ticker = ticker 	# string
		self.domain = domain 	# string
		self.article = None
		self.url = url 			# string
		self.date = None		# datetime.date
		self.sentences = None	# array (string)
		self.words = None		# array (string)
		self.price_init = 0.0	# float
		self.price_t1 = 0.0		# float

	def set_sentences(self, article):
		self.sentences = sent_tokenize(article)

	def set_words(self, article):
		W = word_tokenize(article)
		self.words = [w for w in W if len(w) > 1]

	#def set_prices(self):

class Writer(object):
	"""used to write a list of nodes to the csv file 
	"""
	def __init__(self, nodes, dir_path):
		self.nodes = nodes
		print(self.nodes)
		self.dir_path = dir_path


	def write_nodes(self):
		_path = self.dir_path + 'nodes.csv'
		if os.path.exists(_path):
			append_write = 'a' # append if already exists
		else:
			append_write = 'w' # make a new file if not
		with open(_path, append_write) as _f:
			w = csv.writer(_f)
			if append_write == 'w':
				headers = ['tmp']
				w.writerow(headers)
			data = self.build_node_arr()
			for row in data:
				try:
					w.writerow(row)
				except:
					pass


	def build_node_arr(self):
		n_list = []
		for n in self.nodes:
			if n == None:
				continue 
			d_tmp = n.__dict__ 					# get Node object attributes into a dict
			n_list.append(d_tmp.items())		# convert the dict to an array and append it
		return [n[1] for n in n_list]

class Worker(object):
	def __init__(self, ticker, source, query):
		self.ticker = ticker		# string
		self.source = source		# string
		self.query = query			# string
		self.links = []				# array (string)
		self.nodes = []				# array (Node())
		writer = None 				# Writer() object 

	def set_links(self):
		html = "https://www.google.co.in/search?site=&source=hp&q="+self.query+"&gws_rd=ssl"
		req = urllib2.Request(html, headers={'User-Agent': 'Mozilla/5.0'})
		try:
			soup = BeautifulSoup(urllib2.urlopen(req).read(),"html.parser")
		except (urllib2.HTTPError, urllib2.URLError) as e:
			print "error ", e 
			return 

		#Re to find URLS
		reg=re.compile(".*&sa=")

		#get all web urls from google search result 
		links = []
		for item in soup.find_all(attrs={'class' : 'g'}):
			link = (reg.match(item.a['href'][7:]).group())
			link = link[:-4]
			links.append(link)

		# Check which links are new 
		p = '../data/links.json'
		t = self.ticker.upper()
		with open(p) as _f:
			data = json.load(_f)
		if t in data.keys():
			new_links = [l for l in links if l not in data[t]]
			self.links = new_links
		else:
			# we do not have any links for this ticker yet
			self.links = links

	def update_links(self):
		p = '../data/links.json'
		t = self.ticker.upper()
		new_links = self.links
		with open(p, 'a') as _f:
			data = json.load(_f)
		if t in data.keys():
			original = data[t]
			updated = original + new_links 
			data.update({t : updated})
		else:
			data.update({t : new_links})

		with open(p, 'w') as _f:
			json.dump(data, _f)

	def build_nodes(self):
		for link in self.links:
			node = scrape_link(link, self.ticker)	
			if node != None:
				node.set_sentences(node.article)
				node.set_words(node.article)		
				self.nodes.append(node)



	def get_writer(self, d_path):
		self.writer = Writer(self.nodes, d_path)



# ------------------------------------
#
# WEB SCRAPING METHODS 
#
# ------------------------------------

def check_url(url):
	'''
	ensure the url begins with http
	'''
	valid_schemes = ['http', 'https']
	return urlparse(url).scheme in valid_schemes

def root_path(path):
	while path.dirname(path) != '/':
		path = path.dirname(path)
	return path[1:]

# url = "https://www.bloomberg.com/politics/articles/2017-04-09/melenchon-fillon-tap-momentum-in-quest-of-french-election-upset"
# print root_path(urlparse(url).path)

def find_title(soup):
	'''
	returns the content from the BS4 object if a title tag exists,
	else returns an empty string 
	'''
	title = soup.find("title").contents
	if len(title) > 0:
		return title[0]
	return ""

def _date(date):
	return date['datetime'].strip('\n')

def _article_timestamp(date):
	return date['datetime'].strip('\n')


def find_date(soup):
	'''
	takes in a beautiful soup object and finds the date field
	gets the date value and format dates as %Y-%m-%d %H:%M:%S
	returns a datetime object of this date
	'''
	IDs = ['date','article-timestamp']

	for ID in IDs:
		date = soup.find(class_= ID)
		if date != None:
			currID = ID
			break

	if date == None: return None 

	options = {
		'date':  _date,
		'article-timestamp': _article_timestamp, 
	}

	if currID in options.keys():
		try:  
			return dparser.parse(options[currID](date), fuzzy=True)
		except:
			pass
	return None 

def cname_formatter(cName):
	replace_dict = {'Corporation': ' ', ',': ' ', 'Inc.': ' '} #	to improve query relavence 
	robj = re.compile('|'.join(replace_dict.keys())) 
	return robj.sub(lambda m: replace_dict[m.group(0)], cName) #	returns bare company name

def get_name(symbol):
	"""
	Convert the ticker to the associated company name
	"""
	url = "http://d.yimg.com/autoc.finance.yahoo.com/autoc?query={}&region=1&lang=en".format(symbol)
	result = requests.get(url).json()

	for x in result['ResultSet']['Result']:
		if x['symbol'] == symbol:
			return x['name']

# def bloomberg_parser(soup):

def parse_article(soup, domain):
	'''
	takes in a BS4 object that represents an article embedded in HTML
	returns the article body as a string 
	Currently optimized for: Bloomberg, SeekingAlpha
	'''
	specialized = ['BLOOMBERG']
	if not domain in specialized:
		domain = 'DEFAULT'
	p_offset = {
		'BLOOMBERG': 8,
		'DEFAULT':	 0,
	}
	export_html = ""
	p_tags = soup.find_all('p')
	pre_tags = soup.find_all('pre')
	data = p_tags[p_offset[domain]:] + pre_tags

	for i in data:
		try:
			export_html += i.contents[0]
		except:
			pass

	# check_relavence(html)
	return export_html

def _scrape_link(link, ticker):

	if not check_url(link):
		return -1

	#	OPEN PAGE AND GET THE HTML
	req = urllib2.Request(link, headers={'User-Agent': 'Mozilla/5.0'})
	try:
		page = urllib2.urlopen(req)
	except:
		return -1
	soup = BeautifulSoup(page.read().decode('utf-8', 'ignore'), "html.parser")

	#	PICK APART THE SOUP OBJECT
	url_obj = urlparse(link)
	domain = url_obj.hostname.split('.')[1]
	# root_path = root_path(url_obj.path)
	title = find_title(soup)
	date = find_date(soup)

	n = Node(ticker=ticker, domain=domain, url=link)		#	if we got here, we have successfully parsed the article 
	n.date = date
	n.title = title
	result = parse_article(soup, domain.upper())

	if result < 0:
		return result

	n.article = result
	print ("node is")
	print (n)
	return n

def scrape_link(link, ticker):
	'''
	takes in a ticker and a url and returns the article body as a string 
	as well as the associated change in stock price 
	'''
	result = _scrape_link(link, ticker)

	options = {						#	possible error conditions
		-1: "ERROR -- bad url",	
	}

	if result in options.keys():
		# logger.warn("Error parsing article %s" % options[result])
		return None		#	there was an error

	return result 					#	successful, return a Node object 