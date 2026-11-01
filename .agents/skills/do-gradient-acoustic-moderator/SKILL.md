---
name: do-gradient-acoustic-moderator
description: >-
  DigitalOcean Gradient open-weight AI acoustic analysis skill for Huush.
  Connects ambient room telemetry to Llama 3.1 / Gemma 2 serverless inference
  for non-punitive sound-moderation insights and adaptive threshold tuning.
---

# DigitalOcean Gradient™ AI Acoustic Moderator

Built for the **MLH Hacktoberfest Hack Day Portland** using [DigitalOcean Gradient™ Serverless Inference](https://mlh.link/digitalocean-gradient).

## Overview
Audio never leaves user phones. Only 30-second rolling noise statistics (RMS loudness `0–100`, peak counts, active station labels) are analyzed by an open-weight foundation model (`meta-llama/Meta-Llama-3.1-8B-Instruct` or `google/gemma-2-9b-it`) hosted on DigitalOcean Gradient.

## Environment Variables
Add to `~/.env`:
- `DO_GRADIENT_API_KEY`: Your DigitalOcean GenAI / Gradient Serverless token.
- `DO_GRADIENT_ENDPOINT`: (Default: `https://inference.do-ai.run/v1/chat/completions`)
- `DO_MODEL_NAME`: (Default: `meta-llama/Meta-Llama-3.1-8B-Instruct`)

## How it Bridges to Arduino UNO Q
1. **10 Hz Real-Time Loop**: Physical STM32 13-segment blue LED matrix pulses at 25 Hz based on instantaneous Socket.IO phone levels.
2. **Background AI Modulation**: Every 30 seconds, `python/gradient_ai.py` queries DigitalOcean Gradient to compute ambient room fatigue and dynamically adjust the Arduino's `smoothLevel` HUSH alert threshold.

