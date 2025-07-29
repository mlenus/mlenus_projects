from flask import Flask, request, jsonify
from slack_sdk import WebClient
from apscheduler.schedulers.background import BackgroundScheduler
import atexit
import os
from linkedin_post import build_post_pipeline, post_to_linkedin

# 🔐 Configuration (ideally loaded from environment variables)
SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN")
SLACK_CHANNEL_ID = os.environ.get("SLACK_CHANNEL_ID")
LINKEDIN_ACCESS_TOKEN = os.environ.get("LINKEDIN_ACCESS_TOKEN")
LINKEDIN_AUTHOR_URN = os.environ.get("LINKEDIN_AUTHOR_URN")

app = Flask(__name__)
slack_client = WebClient(token=SLACK_BOT_TOKEN)

# 🧠 Temporary memory to track threads awaiting approval
PENDING_POSTS = {}  # thread_ts → (post_text, asset_urn)

# 🕰️ Scheduler: Send daily prompt
def send_daily_prompt():
    slack_client.chat_postMessage(
        channel=SLACK_CHANNEL_ID,
        text="💡 What topic should I generate a LinkedIn post about today? Reply with `topic: your topic here`."
    )

scheduler = BackgroundScheduler()
scheduler.add_job(send_daily_prompt, "cron", hour=9, minute=0)  # Customize as needed
scheduler.start()
atexit.register(lambda: scheduler.shutdown())

@app.route("/slack/events", methods=["POST"])
def slack_events():
    data = request.json

    # Slack URL verification challenge
    if data.get("type") == "url_verification":
        return jsonify({"challenge": data["challenge"]})

    # Slack Event Callback
    if data.get("type") == "event_callback":
        event = data.get("event", {})
        print(f"📩 Event received: {event}")

        if event.get("type") == "message" and not event.get("subtype") and not event.get("bot_id"):
            event = data.get("event", {})
            text = event.get("text", "")
            print(f"Raw Slack message: {text}", flush=True)
            text = event.get("text", "").strip().lower()
            thread_ts = event.get("thread_ts") or event.get("ts")
            channel = event.get("channel")

            # Initial topic submission
            if "topic:" in text:
                topic = text.split("topic:", 1)[-1].strip()
                print(f"✅ Captured topic: {topic}")

                try:
                    post_text, asset_urn = build_post_pipeline(topic, LINKEDIN_ACCESS_TOKEN, LINKEDIN_AUTHOR_URN)
                    PENDING_POSTS[thread_ts] = (post_text, asset_urn)

                    slack_client.chat_postMessage(
                        channel=channel,
                        thread_ts=thread_ts,
                        text=f"📝 Here's your LinkedIn post draft for *{topic}*:\n\n{post_text}\n\nReply with *yes* to post, or *no* to cancel."
                    )
                except Exception as e:
                    print(f"❌ Error during post generation: {e}")
                    slack_client.chat_postMessage(
                        channel=channel,
                        thread_ts=thread_ts,
                        text="⚠️ Sorry, something went wrong while generating the post."
                    )

            # Approval message (yes/no)
            elif thread_ts in PENDING_POSTS:
                original_post, asset_urn = PENDING_POSTS[thread_ts]

                if text == "yes":
                    try:
                        post_to_linkedin(original_post, asset_urn)
                        slack_client.chat_postMessage(
                            channel=channel,
                            thread_ts=thread_ts,
                            text="✅ Your post has been published to LinkedIn!"
                        )
                        # Optionally, clean up after posting
                        PENDING_POSTS.pop(thread_ts)
                    except Exception as e:
                        print(f"❌ Error posting to LinkedIn: {e}")
                        slack_client.chat_postMessage(
                            channel=channel,
                            thread_ts=thread_ts,
                            text="⚠️ Failed to publish the post to LinkedIn."
                        )

                elif text == "no":
                    slack_client.chat_postMessage(
                        channel=channel,
                        thread_ts=thread_ts,
                        text="🛑 Got it. Your post was not published."
                    )
                    PENDING_POSTS.pop(thread_ts)

                else:
                    # Treat any other message in the thread as an edited post
                    PENDING_POSTS[thread_ts] = (text, asset_urn)
                    slack_client.chat_postMessage(
                        channel=channel,
                        thread_ts=thread_ts,
                        text="✏️ Post updated! Reply with *yes* to publish or *no* to cancel."
                    )

    return "", 200

if __name__ == "__main__":
    print("🚀 Slack event listener running on port 3000...")
    app.run(host="0.0.0.0", port=3000)

