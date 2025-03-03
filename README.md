# Convo-Insight

## Overview

This is an Call Analyzer and email generation platform, its a sales communication tool that automates the analysis of call recordings. Using advanced AI technologies, the platform transcribes calls, performs sentiment analysis, and generates personalized follow-up emails with minimal manual intervention. Built with Django and powered by machine learning models like Whisper and Qwen, this project streamlines sales communication by transforming raw call data into actionable insights.

## Features

- Automated call processing
- Sentiment Analysis
- Intelligent Transcription
- AI-Powered Email generation
- Call insights extraction

## Prerequisites

Last run on these versions

    * MongoDB (v7.0.14)
    * Django (v4.1.13)
    * Python (v3.11.3)
    * SQLite (v3.39.2)
    * Celery (v5.4.0.14.1)
    * Redis (v5.0.14.1)

Important

    * CREATE a `.env file` in the root directory of the project and add all the relevant details needed for the project as per your system.

## How it works

1. Call Upload

    * User uploads an audio recording of a sales call
    * System captures metadata (customer name, company, call type)
    * Initial status set to 'pending'

2. Transcription Process

    * Whisper AI model converts audio to text
    * Performs speaker diarization (identifies different speakers)
    * Stores full transcription in the database

3. Sentiment Analysis

    * AI analyzes the transcribed text
    * Determines overall emotional tone of the call
    * Generates sentiment scores and insights
    * Categorizes sentiment as positive, negative, or neutral

4. Call summarization

    * Extracts key points from the conversation
    * Identifies main discussion topics
    * Captures objections and important details
    * Creates a structured summary of the call

5. Email Generation

    * Uses call insights to craft a personalized follow-up email
    * Adapts tone based on call sentiment
    * Generates subject line and email body
    * Allows customization of email style

6. Additional Features

    * A/B testing for email variants
    * Performance tracking of generated emails
    * Organizational insights and analytics

## Run

1. Clone the repository

    ```bash
    git clone https://github.com/aashishkoundinya/Convo-Insight

2. Install dependencies

    ```bash
    pip install -r requirements.txt

3. Install LLM locally (install the prefered LLM of your choice and edit the LLM model name in download_model.py and config/settings.py)

    ```bash
    python download_model.py

4. Database Setup

    python manage.py makemigrations
    python manage.py migrate
    python manage.py createsuperuser

5. Start Redis (for celery)

    ```bash
    redis-server

6. Start Celery Worker

    ```bash
    celery -A config worker -l INFO --pool=solo

7. Run Django development server

    ```bash
    python manage.py runserver
