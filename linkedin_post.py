# linkedin_post_agent_serper_auto_opinion_with_image.py, I'M USING THIS CELL FOR TESTING. The unedited, working cell that generates and asks for approval in the terminal is the cell above

import requests
import openai
import time
from flask import Flask, render_template_string, request
import threading
import json
import tempfile
import os

import random
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

# Slack configuration
SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN")
SLACK_CHANNEL_ID = os.environ.get("SLACK_CHANNEL_ID")
slack_client = WebClient(token=SLACK_BOT_TOKEN)

FALLBACK_TOPICS = [
    "AI in education",
    "Recent trends in climate tech",
    "The future of ethical AI",
    "How machine learning is changing healthcare",
    "What makes a strong tech resume"
]

# Configuration without Slack starts HERE:

client = openai.OpenAI(
    api_key = os.environ.get("OPENROUTER_API_KEY"),
    base_url="https://openrouter.ai/api/v1"
)

MODEL_NAME = "mistralai/mixtral-8x7b-instruct"

SERPER_API_KEY = os.environ.get("SERPER_API_KEY")

# Your Unsplash API Access Key
UNSPLASH_ACCESS_KEY = "Hri2ni9ACX3XWw26Q72WLcWJx7T3R9q3D0v2mfMiCcY"  # <-- GET THIS from https://unsplash.com/developers

LINKEDIN_ACCESS_TOKEN = os.environ.get("LINKEDIN_ACCESS_TOKEN")
LINKEDIN_AUTHOR_URN = os.environ.get("LINKEDIN_AUTHOR_URN")

# SAFE MODE SETTINGS
SAFE_MODE = True
MAX_ARTICLES = 3
MAX_SNIPPET_LENGTH = 300
MAX_TOKENS_SUMMARY = 500
MAX_TOKENS_POST = 500  # Increased to avoid link cutoff issue

# PREDEFINED OPINIONS
OPINIONS = [
    "AI development must not lead to a loss of human identity or a misunderstanding of our place in the world",
    "Unchecked AI risks undermining human autonomy and enabling harmful misuse",
    "AI must not be treated as a moral agent—it remains a tool, not accountable like a human",
    "AI is ethical only when governed by human reason and moral law—never at the cost of dignity, freedom, or justice",
    "AI must not define human purpose for truth is not found in machines—only reflections"
]

# --- FUNCTIONS ---

def search_articles_serper(topic):
    url = "https://google.serper.dev/search"
    headers = {
        "X-API-KEY": SERPER_API_KEY,
        "Content-Type": "application/json"
    }
    data = {
        "q": topic,
        "num": 5
    }

    resp = requests.post(url, headers=headers, json=data)
    resp.raise_for_status()
    results = resp.json()

    articles = []

    for item in results.get("organic", []):
        title = item.get("title", "")
        link = item.get("link", "")
        snippet = item.get("snippet", "")
        if snippet:
            articles.append({
                "title": title,
                "link": link,
                "snippet": snippet,
                "source": "organic"
            })

    for item in results.get("topStories", []):
        title = item.get("title", "")
        link = item.get("link", "")
        snippet = item.get("snippet", "")
        if snippet:
            articles.append({
                "title": title,
                "link": link,
                "snippet": snippet,
                "source": "topStories"
            })

    return articles

def select_relevant_opinion(snippet_text, opinions):
    opinions_text = "\n".join([f"- {op}" for op in opinions])

    prompt = f"""
    You are an expert analyst. I will give you 5 different opinions about the topic.

    I will also give you article snippets about the topic.

    Please select ONLY ONE opinion from the list that is most relevant to the article snippets.

    Here are the opinions:
    {opinions_text}

    Article snippets:
    {snippet_text}

    Please return ONLY the exact text of the single most relevant opinion.
    """

    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.0,
        max_tokens=50
    )

    return response.choices[0].message.content.strip()

def summarize_with_opinion(snippet_text, opinion):
    prompt = f"""
    You are an expert writer. I will give you article snippets and an opinion.
    Your job is to extract 2-3 key points from the snippets that SUPPORT the opinion.

    Opinion: "{opinion}"

    Article snippets: {snippet_text}

    Please return 2-3 key points that strongly support the opinion.
    """

    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.5,
        max_tokens=MAX_TOKENS_SUMMARY
    )

    return response.choices[0].message.content.strip()

def compose_linkedin_post(points_text, opinion, title_links_text):
    prompt = f"""
    You are a motivated and inquisitive college student that is eager to learn and trying to make a solid impression on LinkedIn. 
    Using the following key points, create a LinkedIn (or blog, or newsletter) post, pertinent to the opinion, that includes clickable links 
    to these articles, using their short names or titles as anchor text.
    Make it friendly, conversational, persuasive, and ask probing questions. Keep the tone of the post humble. Don't explicity mention that you're 
    a college student and don't state the opinion you're using verbatum!
    Here are the available titles and links you may use:

    {title_links_text}

    Opinion: "{opinion}"

    Supporting Points: {points_text}

    The post should sound professional, credible, and insightful.
    """

    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        max_tokens=MAX_TOKENS_POST
    )

    return response.choices[0].message.content.strip()

QUERY_KEYWORDS = {
    "medicine": "medical technology hospital doctor AI healthcare",
    "ethics": "ai ethics brain balance scales responsibility justice",
    "identity": "human face biometric scanner digital human AI",
    "privacy": "cybersecurity lock data protection AI surveillance",
    "innovation": "ai innovation robots lab future technology"
}

def build_query_from_opinion(opinion_text):
    if "medicine" in opinion_text.lower():
        return QUERY_KEYWORDS["medicine"]
    elif "privacy" in opinion_text.lower():
        return QUERY_KEYWORDS["privacy"]
    elif "ethics" in opinion_text.lower():
        return QUERY_KEYWORDS["ethics"]
    elif "identity" in opinion_text.lower():
        return QUERY_KEYWORDS["identity"]
    elif "innovation" in opinion_text.lower():
        return QUERY_KEYWORDS["innovation"]
    else:
        return "AI technology future"

def search_unsplash_image(query):
    """Searches Unsplash for a relevant image based on the query and returns the image URL."""
    url = "https://api.unsplash.com/search/photos"
    params = {
        "query": query,
        "per_page": 1,
        "orientation": "landscape"
    }
    headers = {
        "Authorization": f"Client-ID {UNSPLASH_ACCESS_KEY}"
    }

    resp = requests.get(url, headers=headers, params=params)
    resp.raise_for_status()
    results = resp.json()

    if results.get("results"):
        image_url = results["results"][0]["urls"]["regular"]
        return image_url
    else:
        return None

def register_image_upload(access_token, author_urn):
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "X-Restli-Protocol-Version": "2.0.0"
    }
    data = {
        "registerUploadRequest": {
            "owner": author_urn,
            "recipes": ["urn:li:digitalmediaRecipe:feedshare-image"],
            "serviceRelationships": [
                {
                    "relationshipType": "OWNER",
                    "identifier": "urn:li:userGeneratedContent"
                }
            ]
        }
    }
    resp = requests.post("https://api.linkedin.com/v2/assets?action=registerUpload",
                         headers=headers, data=json.dumps(data))
    resp.raise_for_status()
    value = resp.json()["value"]
    return value["uploadMechanism"]["com.linkedin.digitalmedia.uploading.MediaUploadHttpRequest"]["uploadUrl"], value["asset"]

def upload_image(upload_url, image_path):
    with open(image_path, "rb") as img_file:
        headers = {
            "Content-Type": "application/octet-stream"
        }
        resp = requests.put(upload_url, headers=headers, data=img_file)
        resp.raise_for_status()

def upload_image_to_linkedin(image_url, access_token, author_urn):
    img_resp = requests.get(image_url)
    img_resp.raise_for_status()
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
    temp_file.write(img_resp.content)
    temp_file.close()
    upload_url, asset_urn = register_image_upload(access_token, author_urn)
    upload_image(upload_url, temp_file.name)
    return asset_urn

def post_to_linkedin(post_text, asset_urn=None):
    headers = {
        "Authorization": f"Bearer {access_token}",
        "X-Restli-Protocol-Version": "2.0.0",
        "Content-Type": "application/json"
    }
    post_data = {
        "author": author_urn,
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {"text": post_text}
            }
        },
        "visibility": {
            "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"
        }
    }

    if asset_urn:
        post_data["specificContent"]["com.linkedin.ugc.ShareContent"]["shareMediaCategory"] = "IMAGE"
        post_data["specificContent"]["com.linkedin.ugc.ShareContent"]["media"] = [{
            "status": "READY",
            "media": asset_urn
        }]
    else:
        post_data["specificContent"]["com.linkedin.ugc.ShareContent"]["shareMediaCategory"] = "NONE"

    resp = requests.post("https://api.linkedin.com/v2/ugcPosts", headers=headers, data=json.dumps(post_data))
    if resp.status_code == 201:
        print("🎉 Post published successfully!")
    else:
        print("❌ Error posting:", resp.status_code, resp.text)

def build_post_pipeline(topic, access_token, author_urn):
    articles = search_articles_serper(topic)
    articles = articles[:MAX_ARTICLES] if SAFE_MODE else articles

    snippet_block = ""
    title_link_map = {}

    for article in articles:
        snippet = article["snippet"][:MAX_SNIPPET_LENGTH]
        snippet_block += f"Title: {article['title']}\nSnippet: {snippet}\n\n"
        title_link_map[article['title']] = article['link']
        time.sleep(0.5)

    title_links_text = "\n".join([f"[{title}]({link})" for title, link in title_link_map.items()])
    opinion = select_relevant_opinion(snippet_block, OPINIONS)
    points = summarize_with_opinion(snippet_block, opinion)
    post_text = compose_linkedin_post(points, opinion, title_links_text)
    query = build_query_from_opinion(opinion)
    image_url = search_unsplash_image(query)
    asset_urn = upload_image_to_linkedin(image_url, access_token, author_urn) if image_url else None

    return post_text, asset_urn
