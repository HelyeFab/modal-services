# VOICEVOX TTS Service on Modal

Japanese text-to-speech service using the official VOICEVOX engine, deployed on Modal.com.

## Overview

This service provides high-quality Japanese TTS with 113 voices. It wraps the official VOICEVOX Docker image (`voicevox/voicevox_engine:cpu-latest`) with an OpenAI-compatible API layer.

## Endpoint

```
https://emmanuelfabiani23--voicevox-tts-serve.modal.run
```

## Authentication

All endpoints (except `/health`) require the `X-API-Key` header.

```bash
X-API-Key: <your-api-key>
```

The API key is stored in Modal secret `moshimoshi-api-key`.

## API Usage

### Generate Speech

```bash
curl -X POST "https://emmanuelfabiani23--voicevox-tts-serve.modal.run/v1/audio/speech" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: YOUR_API_KEY" \
  -d '{"input": "こんにちは、世界。", "voice": "11"}' \
  -o output.wav
```

**Request Body:**
| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `input` | string | required | Japanese text to synthesize |
| `voice` | string | "1" | Speaker ID (see voice list below) |
| `speed` | float | 1.0 | Speech speed multiplier |
| `model` | string | "voicevox" | Model name (ignored, for OpenAI compatibility) |

**Response:** WAV audio file (16-bit PCM, 24000 Hz, mono)

### List Voices

```bash
curl "https://emmanuelfabiani23--voicevox-tts-serve.modal.run/v1/audio/voices"
```

### Health Check

```bash
curl "https://emmanuelfabiani23--voicevox-tts-serve.modal.run/health"
```

## Recommended Adult Voices

### Male Adults
| ID | Name | Description |
|----|------|-------------|
| 11 | 玄野武宏 (ノーマル) | Deep adult male voice |
| 13 | 青山龍星 (ノーマル) | Adult male |
| 52 | 雀松朱司 (ノーマル) | Adult male |
| 53 | 麒ヶ島宗麟 (ノーマル) | Adult male |

### Female Adults
| ID | Name | Description |
|----|------|-------------|
| 2 | 四国めたん (ノーマル) | Adult female |
| 4 | 四国めたん (セクシー) | Mature female |
| 8 | 春日部つむぎ (ノーマル) | Adult female |
| 9 | 波音リツ (ノーマル) | Adult female |
| 46 | 小夜/SAYO (ノーマル) | Adult female |

## Complete Voice List (113 voices)

### 四国めたん (Shikoku Metan) - Female
| ID | Style |
|----|-------|
| 2 | ノーマル |
| 0 | あまあま |
| 6 | ツンツン |
| 4 | セクシー |
| 36 | ささやき |
| 37 | ヒソヒソ |

### ずんだもん (Zundamon) - Mascot (child-like)
| ID | Style |
|----|-------|
| 3 | ノーマル |
| 1 | あまあま |
| 7 | ツンツン |
| 5 | セクシー |
| 22 | ささやき |
| 38 | ヒソヒソ |
| 75 | ヘロヘロ |
| 76 | なみだめ |

### 春日部つむぎ (Kasukabe Tsumugi) - Female
| ID | Style |
|----|-------|
| 8 | ノーマル |

### 雨晴はう (Amehare Hau) - Female
| ID | Style |
|----|-------|
| 10 | ノーマル |

### 波音リツ (Namine Ritsu) - Female
| ID | Style |
|----|-------|
| 9 | ノーマル |
| 65 | クイーン |

### 玄野武宏 (Kurono Takehiro) - Male Adult
| ID | Style |
|----|-------|
| 11 | ノーマル |
| 39 | 喜び |
| 40 | ツンギレ |
| 41 | 悲しみ |

### 白上虎太郎 (Shirakami Kotaro) - Male
| ID | Style |
|----|-------|
| 12 | ふつう |
| 32 | わーい |
| 33 | びくびく |
| 34 | おこ |
| 35 | びえーん |

### 青山龍星 (Aoyama Ryusei) - Male Adult
| ID | Style |
|----|-------|
| 13 | ノーマル |
| 81 | 熱血 |
| 82 | 不機嫌 |
| 83 | 喜び |
| 84 | しっとり |
| 85 | かなしみ |
| 86 | 囁き |

### 冥鳴ひまり (Meimei Himari) - Female
| ID | Style |
|----|-------|
| 14 | ノーマル |

### 九州そら (Kyushu Sora) - Female
| ID | Style |
|----|-------|
| 16 | ノーマル |
| 15 | あまあま |
| 18 | ツンツン |
| 17 | セクシー |
| 19 | ささやき |

### もち子さん (Mochiko-san) - Female
| ID | Style |
|----|-------|
| 20 | ノーマル |
| 66 | セクシー／あん子 |
| 77 | 泣き |
| 78 | 怒り |
| 79 | 喜び |
| 80 | のんびり |

### 剣崎雌雄 (Kenzaki Mesuo) - Male
| ID | Style |
|----|-------|
| 21 | ノーマル |

### WhiteCUL - Female
| ID | Style |
|----|-------|
| 23 | ノーマル |
| 24 | たのしい |
| 25 | かなしい |
| 26 | びえーん |

### 後鬼 (Goki)
| ID | Style |
|----|-------|
| 27 | 人間ver. |
| 28 | ぬいぐるみver. |
| 87 | 人間（怒り）ver. |
| 88 | 鬼ver. |

### No.7
| ID | Style |
|----|-------|
| 29 | ノーマル |
| 30 | アナウンス |
| 31 | 読み聞かせ |

### ちび式じい (Chibishiki Jii) - Elderly Male
| ID | Style |
|----|-------|
| 42 | ノーマル |

### 櫻歌ミコ (Ohka Miko) - Female
| ID | Style |
|----|-------|
| 43 | ノーマル |
| 44 | 第二形態 |
| 45 | ロリ |

### 小夜/SAYO - Female Adult
| ID | Style |
|----|-------|
| 46 | ノーマル |

### ナースロボ＿タイプＴ (Nurse Robot Type T)
| ID | Style |
|----|-------|
| 47 | ノーマル |
| 48 | 楽々 |
| 49 | 恐怖 |
| 50 | 内緒話 |

### †聖騎士 紅桜† (Holy Knight Kurozakura) - Male
| ID | Style |
|----|-------|
| 51 | ノーマル |

### 雀松朱司 (Suzumatsu Akashi) - Male Adult
| ID | Style |
|----|-------|
| 52 | ノーマル |

### 麒ヶ島宗麟 (Kigashima Sorin) - Male Adult
| ID | Style |
|----|-------|
| 53 | ノーマル |

### 春歌ナナ (Haruka Nana) - Female
| ID | Style |
|----|-------|
| 54 | ノーマル |

### 猫使アル (Nekotukai Aru) - Female
| ID | Style |
|----|-------|
| 55 | ノーマル |
| 56 | おちつき |
| 57 | うきうき |
| 110 | つよつよ |
| 111 | へろへろ |

### 猫使ビィ (Nekotukai Bi) - Female
| ID | Style |
|----|-------|
| 58 | ノーマル |
| 59 | おちつき |
| 60 | 人見知り |
| 112 | つよつよ |

### 中国うさぎ (Chugoku Usagi) - Female
| ID | Style |
|----|-------|
| 61 | ノーマル |
| 62 | おどろき |
| 63 | こわがり |
| 64 | へろへろ |

### 栗田まろん (Kurita Maron) - Female
| ID | Style |
|----|-------|
| 67 | ノーマル |

### あいえるたん (Aieruran) - Female
| ID | Style |
|----|-------|
| 68 | ノーマル |

### 満別花丸 (Manbetsu Hanamaru)
| ID | Style |
|----|-------|
| 69 | ノーマル |
| 70 | 元気 |
| 71 | ささやき |
| 72 | ぶりっ子 |
| 73 | ボーイ |

### 琴詠ニア (Kotoyomi Nia) - Female
| ID | Style |
|----|-------|
| 74 | ノーマル |

### Voidoll
| ID | Style |
|----|-------|
| 89 | ノーマル |

### ぞん子 (Zonko) - Female
| ID | Style |
|----|-------|
| 90 | ノーマル |
| 91 | 低血圧 |
| 92 | 覚醒 |
| 93 | 実況風 |

### 中部つるぎ (Chubu Tsurugi) - Female
| ID | Style |
|----|-------|
| 94 | ノーマル |
| 95 | 怒り |
| 96 | ヒソヒソ |
| 97 | おどおど |
| 98 | 絶望と敗北 |

### 離途 (Rito)
| ID | Style |
|----|-------|
| 99 | ノーマル |
| 101 | シリアス |

### 黒沢冴白 (Kurosawa Saehaku)
| ID | Style |
|----|-------|
| 100 | ノーマル |

### ユーレイちゃん (Yurei-chan) - Female
| ID | Style |
|----|-------|
| 102 | ノーマル |
| 103 | 甘々 |
| 104 | 哀しみ |
| 105 | ささやき |
| 106 | ツクモちゃん |

### 東北ずん子 (Tohoku Zunko) - Female
| ID | Style |
|----|-------|
| 107 | ノーマル |

### 東北きりたん (Tohoku Kiritan) - Female
| ID | Style |
|----|-------|
| 108 | ノーマル |

### 東北イタコ (Tohoku Itako) - Female
| ID | Style |
|----|-------|
| 109 | ノーマル |

## Deployment

Deploy using WSL to avoid Windows encoding issues:

```bash
wsl bash -c "cd /mnt/c/Users/esfab/WinDevProjects/modal-services/voicevox-tts && python3 -m modal deploy deploy_voicevox.py"
```

## Architecture

- **Base Image:** `voicevox/voicevox_engine:cpu-latest`
- **Resources:** 4 CPU, 8GB RAM
- **Timeout:** 600s
- **Scale:** min 0, scaledown after 300s idle
- **Internal:** VOICEVOX engine runs on port 50021, FastAPI wrapper proxies requests

## Python Client Example

```python
import httpx
import os

API_KEY = os.environ.get("MODAL_API_KEY")

def speak_japanese(text: str, voice_id: str = "11") -> bytes:
    """Generate Japanese speech audio."""
    response = httpx.post(
        "https://emmanuelfabiani23--voicevox-tts-serve.modal.run/v1/audio/speech",
        json={"input": text, "voice": voice_id},
        headers={"X-API-Key": API_KEY},
        timeout=120
    )
    response.raise_for_status()
    return response.content

# Save to file
audio = speak_japanese("こんにちは、世界。今日はいい天気ですね。", voice_id="11")
with open("output.wav", "wb") as f:
    f.write(audio)
```

## Credits

VOICEVOX is free text-to-speech software. When using generated audio, credit must be given as:
`VOICEVOX:{character name}`

See individual character license terms in the VOICEVOX README.
