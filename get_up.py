import argparse
import os
import random

import openai
import pendulum
import requests
from BingImageCreator import ImageGen
from github import Github
from bardapi import Bard


# 14 for test 12 real get up
GET_UP_ISSUE_NUMBER = 12
GET_UP_MESSAGE_TEMPLATE = "今天的起床时间是--{get_up_time}.\r\n\r\n 起床啦，喝杯咖啡，背个单词，去跑步。\r\n\r\n 今天的一句诗:\r\n {sentence} \r\n"
SENTENCE_API = "https://v1.jinrishici.com/all"
DEFAULT_SENTENCE = "赏花归去马如飞\r\n去马如飞酒力微\r\n酒力微醒时已暮\r\n醒时已暮赏花归\r\n"
TIMEZONE = "Asia/Shanghai"
PROMPT = "请帮我把这个句子 `{sentence}` 翻译成英语，请按描述绘画的方式翻译，只返回翻译后的句子"
BARD_IMAGE_PROMPT = "Write me a line from an old Chinese poem based on this picture. only return this line in simplified Chinese."


def login(token):
    return Github(token)


def get_one_sentence():
    try:
        r = requests.get(SENTENCE_API)
        if r.ok:
            return r.json().get("content", DEFAULT_SENTENCE)
        return DEFAULT_SENTENCE
    except:
        print("get SENTENCE_API wrong")
        return DEFAULT_SENTENCE


def get_today_get_up_status(issue):
    comments = list(issue.get_comments())
    if not comments:
        return False
    latest_comment = comments[-1]
    now = pendulum.now(TIMEZONE)
    latest_day = pendulum.instance(latest_comment.created_at).in_timezone(
        "Asia/Shanghai"
    )
    is_today = (latest_day.day == now.day) and (latest_day.month == now.month)
    return is_today


def make_pic_and_save(sentence_en, bing_cookie, bard_token):
    """
    return the link for md
    """
    # do not add text on the png
    sentence_en = sentence_en + ", textless"
    i = ImageGen(bing_cookie)
    images = i.get_images(sentence_en)
    date_str = pendulum.now().to_date_string()
    new_path = os.path.join("OUT_DIR", date_str)
    bard_explain = ""
    if not os.path.exists(new_path):
        os.mkdir(new_path)
    # download count = 4
    i.save_images(images, new_path)
    index = random.randint(0, 3)
    try:
        with open(os.path.join(new_path, str(index) + ".jpeg"), "rb") as f:
            bard = Bard(token=bard_token)
            bard_answer = bard.ask_about_image(BARD_IMAGE_PROMPT, f.read())
            print(bard_answer["content"])
            bard_explain = bard_answer["content"]

    except Exception as e:
        print(str(e))
    return images[index], bard_explain


def make_get_up_message(bing_cookie, bard_token):
    sentence = get_one_sentence()
    now = pendulum.now(TIMEZONE)
    # 3 - 7 means early for me
    is_get_up_early = 3 <= now.hour <= 7
    get_up_time = now.to_datetime_string()
    ms = [{"role": "user", "content": PROMPT.format(sentence=sentence)}]
    completion = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=ms,
    )
    sentence_en = (
        completion["choices"][0].get("message").get("content").encode("utf8").decode()
    )
    link = ""
    bard_explain = ""
    try:
        link, bard_explain = make_pic_and_save(sentence_en, bing_cookie, bard_token)
    except Exception as e:
        print(str(e))
        # give it a second chance
        try:
            sentence = get_one_sentence()
            print(f"Second: {sentence}")
            ms = [{"role": "user", "content": PROMPT.format(sentence=sentence)}]
            completion = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=ms,
            )
            sentence_en = (
                completion["choices"][0]
                .get("message")
                .get("content")
                .encode("utf8")
                .decode()
            )
            link, bard_explain = make_pic_and_save(sentence_en, bing_cookie, bard_token)
        except Exception as e:
            print(str(e))
    body = GET_UP_MESSAGE_TEMPLATE.format(
        get_up_time=get_up_time, sentence=sentence, link=link
    )
    body_explain = ""
    if bard_explain:
        body_explain = "Bard: \n" + bard_explain
    print(body, link)
    return body, body_explain, is_get_up_early, link


def main(
    github_token,
    repo_name,
    weather_message,
    bing_cookie,
    bard_token,
    tele_token,
    tele_chat_id,
):
    u = login(github_token)
    repo = u.get_repo(repo_name)
    issue = repo.get_issue(GET_UP_ISSUE_NUMBER)
    is_today = get_today_get_up_status(issue)
    if is_today:
        print("Today I have recorded the wake up time")
        return
    early_message, body_explain, is_get_up_early, link = make_get_up_message(
        bing_cookie, bard_token
    )
    body = early_message
    if weather_message:
        weather_message = f"现在的天气是{weather_message}\n"
        body = weather_message + early_message
    if is_get_up_early:
        comment = body + f"![image]({link})" + "\n" + body_explain
        issue.create_comment(comment)
        # send to telegram
        if tele_token and tele_chat_id:
            requests.post(
                url="https://api.telegram.org/bot{0}/{1}".format(
                    tele_token, "sendPhoto"
                ),
                data={
                    "chat_id": tele_chat_id,
                    "photo": link or "https://pp.qianp.com/zidian/kai/27/65e9.png",
                    "caption": body,
                },
            )
    else:
        print("You wake up late")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("github_token", help="github_token")
    parser.add_argument("repo_name", help="repo_name")
    parser.add_argument(
        "--weather_message", help="weather_message", nargs="?", default="", const=""
    )
    parser.add_argument(
        "--bing_cookie", help="bing_cookie", nargs="?", default="", const=""
    )
    parser.add_argument(
        "--bard_token", help="bing_cookie", nargs="?", default="", const=""
    )
    parser.add_argument(
        "--tele_token", help="tele_token", nargs="?", default="", const=""
    )
    parser.add_argument(
        "--tele_chat_id", help="tele_chat_id", nargs="?", default="", const=""
    )
    options = parser.parse_args()
    main(
        options.github_token,
        options.repo_name,
        options.weather_message,
        options.bing_cookie,
        options.bard_token,
        options.tele_token,
        options.tele_chat_id,
    )
