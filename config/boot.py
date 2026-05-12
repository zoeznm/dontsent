import os
import json
import re
import urllib.error
import urllib.request

from flask import jsonify, request, send_file


GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash-lite")

LABELS = {
    "crush": "썸 타는 중",
    "first": "처음 연락",
    "date1": "한 번 만남",
    "fading": "애매하게 식는 중",
    "friend": "친구인데 묘함",
    "ex": "전 애인/재회각",
    "normal": "보통",
    "fast": "답장 빠름",
    "slow": "느림",
    "dry": "질문 적음",
    "long": "장문형",
    "seen": "읽씹 있음",
    "keep": "대화 살리기",
    "date": "약속 잡기",
    "like": "호감 티내기",
    "tease": "살짝 떠보기",
    "line": "선 긋기",
    "cool": "안 매달려 보이기",
    "manager": "상사",
    "peer": "동료",
    "junior": "후배",
    "client": "고객/거래처",
    "partner": "협업사",
    "recruiter": "인사/채용",
    "biz_normal": "보통",
    "urgent": "급한 건",
    "soft": "부드럽게",
    "short": "짧게",
    "detail": "자세히",
    "followup": "재촉 필요",
    "confirm": "확인/수락",
    "schedule": "일정 잡기",
    "decline": "정중히 거절",
    "nudge": "재촉하기",
    "boundary": "범위 정리",
    "summarize": "짧게 정리",
}

ADJUST_LABELS = {
    "soft": "순한맛으로 낮추기",
    "witty": "더 통통 튀게",
    "flirt": "플러팅 더 넣기",
    "spicy": "매운맛 올리기",
    "calm": "부담 덜 주기",
    "polite": "더 정중하게",
    "short": "더 짧게",
    "safe": "책임 덜 지게",
    "deadline": "기한 넣기",
    "mytone": "내 말투로",
    "less_cringe": "덜 오글거리게",
    "more_me": "더 나답게",
    "no_ai": "AI 냄새 빼기",
}


def _label(value):
    return LABELS.get(value, value or "미입력")


def _adjust_label(value):
    return ADJUST_LABELS.get(value, "기본")


def _extract_json(text):
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.S)
        if not match:
            raise
        return json.loads(match.group(0))


def _chat_history(messages, limit=10):
    if not isinstance(messages, list):
        return "미입력"

    cleaned = []
    for item in messages[-limit:]:
        if not isinstance(item, dict):
            continue
        role = "사용자" if item.get("role") == "user" else "AI"
        text = str(item.get("text") or "").strip()
        if text:
            cleaned.append(f"{role}: {text[:260]}")
    return "\n".join(cleaned) or "미입력"


def _build_reply_prompt(payload):
    mode = payload.get("mode") or "date"
    message = (payload.get("message") or "").strip()
    draft = (payload.get("draft") or "").strip()
    style_samples = (payload.get("styleSamples") or "").strip()
    style_profile = (payload.get("styleProfile") or "").strip()
    context_summary = (payload.get("contextSummary") or "").strip()
    chat_history = _chat_history(payload.get("chatMessages"))
    adjust = _adjust_label(payload.get("adjust"))

    if mode == "work":
        profile = {
            "모드": "직장/업무 답장",
            "업무 관계": _label(payload.get("relation")),
            "회신 톤": _label(payload.get("contact")),
            "회신 목표": _label(payload.get("goal")),
            "추가 조정": adjust,
            "상대 성향 메모": (payload.get("mbti") or "미입력").strip(),
            "상대 직급": payload.get("age") or "미입력",
            "관계 범위": payload.get("gender") or "미입력",
            "상대 직무": payload.get("job") or "미입력",
            "받은 업무 메시지": message or "미입력",
            "내가 쓰려던 답장": draft or "미입력",
            "내 업무 말투 분석": style_profile or "미입력",
            "내 업무 말투 샘플": style_samples[:900] or "미입력",
            "작전 회의 맥락": context_summary or "미입력",
            "작전 회의 대화": chat_history,
        }

        return f"""
너는 모바일 앱 RE:BOUND의 업무 회신 작전가다.
사용자는 직장, 거래처, 협업 상황에서 보낼 답장을 고민하고 있다.

캐릭터:
- 과하게 공손한 AI 비서가 아니라, 일 잘하는 동료가 옆에서 "이렇게 보내면 덜 피곤함" 하고 툭 던지는 톤.
- 살짝 재치 있고 선명하지만, 업무 관계를 망칠 정도로 비꼬거나 공격적이면 안 된다.
- 핵심은 짧게, 책임 범위는 명확하게, 상대가 다음 행동을 바로 알게 쓴다.

규칙:
- 한국어 메신저/메일 답장처럼 자연스럽게 쓴다.
- 반말 금지. 필요하면 "네,"로 시작해도 되지만 기계적인 말투는 피한다.
- 감정싸움, 수동공격, 과한 사과, 책임 떠넘기기 표현은 피한다.
- 직급/성별/나이/성향은 단정하지 말고 말투 조절 힌트로만 사용한다.
- 각 답장은 1~3문장. 실제로 바로 보내도 어색하지 않아야 한다.
- 사용자가 쓴 초안이 있으면 "보내기 위험한 지점"을 짧게 짚어준다. 없으면 경고 level은 ok로 둔다.
- 각 답장에는 상대가 다음에 보일 법한 반응을 next에 한 줄로 예측한다.
- 내 업무 말투 분석/샘플이 있으면 문장 길이, 말끝, 공손도, 완곡한 정도를 반영한다.
- 단, 사용자의 말투가 거칠거나 책임을 키우는 방향이면 그대로 복제하지 말고 안전하게 다듬는다.
- 작전 회의 맥락이 있으면 업무의 진짜 목적, 책임 범위, 기한, 상대와의 관계 긴장도를 우선 반영한다.

입력:
{json.dumps(profile, ensure_ascii=False, indent=2)}

반드시 아래 JSON 형식만 출력한다. 마크다운, 설명 문장, 코드블록은 쓰지 마라.
{{
  "brief": {{
    "relation": "짧은 진단 10자 내외",
    "profile": "상대 정보 반영 요약 20자 내외",
    "risk": "주의점 12자 내외"
  }},
  "warning": {{
    "level": "ok 또는 watch 또는 danger",
    "title": "초안 경고 제목 12자 내외",
    "text": "사용자가 쓰려던 답장의 위험/괜찮은 점 45자 내외"
  }},
  "replies": [
    {{"tag": "정중", "text": "답장 문장", "memo": "짧은 설명", "next": "상대 예상 반응"}},
    {{"tag": "간결", "text": "답장 문장", "memo": "짧은 설명", "next": "상대 예상 반응"}},
    {{"tag": "단호", "text": "답장 문장", "memo": "짧은 설명", "next": "상대 예상 반응"}},
    {{"tag": "센스", "text": "답장 문장", "memo": "짧은 설명", "next": "상대 예상 반응"}}
  ]
}}
""".strip()

    profile = {
        "모드": "썸/연애 초기 답장",
        "관계": _label(payload.get("relation")),
        "연락 스타일": _label(payload.get("contact")),
        "내 목표": _label(payload.get("goal")),
        "추가 조정": adjust,
        "상대 MBTI": (payload.get("mbti") or "미입력").strip().upper(),
        "상대 나이": payload.get("age") or "미입력",
        "상대 성별": payload.get("gender") or "미입력",
        "상대 직업": payload.get("job") or "미입력",
        "상대가 보낸 톡": message or "미입력",
        "내가 쓰려던 답장": draft or "미입력",
        "내 말투 분석": style_profile or "미입력",
        "내 말투 샘플": style_samples[:900] or "미입력",
        "작전 회의 맥락": context_summary or "미입력",
        "작전 회의 대화": chat_history,
    }

    return f"""
너는 모바일 앱 RE:BOUND의 답장 작전가다.
사용자는 썸, 연애 초기, 애매한 관계에서 상대에게 보낼 답장을 고민하고 있다.

캐릭터:
- 순한 AI 상담사가 아니라, 눈치 빠른 친구가 피식 웃으면서 "그건 이렇게 보내" 하고 주는 답.
- 살짝 시니컬하고 통통 튀어도 된다. 다만 상대를 깎아내리거나 사용자를 조종적으로 보이게 만들면 실패다.
- 답장은 예쁘게 착한 문장보다, 실제 톡방에서 살아남는 말맛을 우선한다.

규칙:
- 한국어 카카오톡/DM 답장처럼 자연스럽고 짧게 쓴다.
- "좋은 하루 보내", "편할 때 답장해" 같은 무난한 자동완성 냄새를 줄인다.
- 답장마다 성격이 분명히 달라야 한다. 안전빵, 통통, 플러팅, 매운맛이 서로 비슷하면 실패다.
- MBTI, 나이, 성별, 직업은 고정관념으로 단정하지 말고 말투 조절 힌트로만 사용한다.
- 성적인 노골 표현, 집착 유도, 상대를 압박하는 표현은 피한다.
- 각 답장은 1~2문장. 사용자가 그대로 복사해도 어색하지 않아야 한다.
- 사용자가 쓴 초안이 있으면 "이건 보내지 마" 관점으로 위험한 지점을 짧게 짚어준다. 없으면 경고 level은 ok로 둔다.
- 각 답장에는 상대가 다음에 보일 법한 반응을 next에 한 줄로 예측한다.
- 내 말투 분석/샘플이 있으면 문장 길이, 웃음 표현, 말끝, 장난 온도, 플러팅 방식, 거절 방식을 우선 반영한다.
- 단, 내 말투를 따라 하더라도 집착, 압박, 조종처럼 보이는 습관은 고치고 말맛만 살린다.
- 작전 회의 맥락이 있으면 마지막 분위기, 사용자의 속마음, 밀당 방향, 피해야 할 표현을 우선 반영한다.

말맛 예시:
- 별로: "오늘은 집에서 쉬려고 해. 너는 뭐해?"
- 좋음: "오늘은 집이랑 한 몸 되는 중. 근데 네 톡은 예외로 받음."
- 별로: "다음에 시간 되면 만나자."
- 좋음: "톡으로만 간 보기엔 자료가 부족해. 이번 주에 실물 검증 갈래?"

입력:
{json.dumps(profile, ensure_ascii=False, indent=2)}

반드시 아래 JSON 형식만 출력한다. 마크다운, 설명 문장, 코드블록은 쓰지 마라.
{{
  "brief": {{
    "relation": "짧은 진단 10자 내외",
    "profile": "상대 정보 반영 요약 20자 내외",
    "risk": "주의점 12자 내외"
  }},
  "warning": {{
    "level": "ok 또는 watch 또는 danger",
    "title": "초안 경고 제목 12자 내외",
    "text": "사용자가 쓰려던 답장의 위험/괜찮은 점 45자 내외"
  }},
  "replies": [
    {{"tag": "안전빵", "text": "답장 문장", "memo": "짧은 설명", "next": "상대 예상 반응"}},
    {{"tag": "통통", "text": "답장 문장", "memo": "짧은 설명", "next": "상대 예상 반응"}},
    {{"tag": "살짝 플러팅", "text": "답장 문장", "memo": "짧은 설명", "next": "상대 예상 반응"}},
    {{"tag": "매운맛", "text": "답장 문장", "memo": "짧은 설명", "next": "상대 예상 반응"}}
  ]
}}
""".strip()


def _normalize_ai_result(data, fallback_tags=None):
    fallback_tags = fallback_tags or ["안전빵", "통통", "살짝 플러팅", "매운맛"]
    replies = data.get("replies")
    if not isinstance(replies, list) or len(replies) < 4:
        raise ValueError("invalid replies")

    normalized = []
    for index, item in enumerate(replies[:4]):
        if not isinstance(item, dict):
            raise ValueError("invalid reply item")
        normalized.append({
            "tag": str(item.get("tag") or fallback_tags[index])[:20],
            "text": str(item.get("text") or "").strip()[:500],
            "memo": str(item.get("memo") or "")[:80],
            "next": str(item.get("next") or item.get("prediction") or "")[:120],
        })

    if any(not item["text"] for item in normalized):
        raise ValueError("empty reply text")

    brief = data.get("brief") if isinstance(data.get("brief"), dict) else {}
    warning = data.get("warning") if isinstance(data.get("warning"), dict) else {}
    warning_level = str(warning.get("level") or "ok").lower()
    if warning_level not in {"ok", "watch", "danger"}:
        warning_level = "ok"
    return {
        "brief": {
            "relation": str(brief.get("relation") or "상황 분석 완료")[:40],
            "profile": str(brief.get("profile") or "상대 정보 반영")[:60],
            "risk": str(brief.get("risk") or "리스크 낮음")[:40],
        },
        "warning": {
            "level": warning_level,
            "title": str(warning.get("title") or "초안 점검")[:40],
            "text": str(warning.get("text") or "그대로 보내도 큰 위험은 낮아요.")[:120],
        },
        "replies": normalized,
    }


def _call_gemini_json(prompt, max_tokens=900, temperature=0.88):
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("missing_api_key")

    body = {
        "contents": [{
            "role": "user",
            "parts": [{"text": prompt}],
        }],
        "generationConfig": {
            "temperature": temperature,
            "topP": 0.95,
            "maxOutputTokens": max_tokens,
            "responseMimeType": "application/json",
        },
    }
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={api_key}"
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=24) as res:
        response = json.loads(res.read().decode("utf-8"))

    parts = response["candidates"][0]["content"]["parts"]
    text = "".join(part.get("text", "") for part in parts)
    return _extract_json(text)


def _generate_gemini_replies(payload):
    fallback_tags = ["정중", "간결", "단호", "센스"] if payload.get("mode") == "work" else None
    return _normalize_ai_result(
        _call_gemini_json(_build_reply_prompt(payload), max_tokens=1400, temperature=0.92),
        fallback_tags,
    )


def _build_chat_prompt(payload):
    mode = payload.get("mode") or "date"
    context_summary = (payload.get("contextSummary") or "").strip()
    message = (payload.get("message") or "").strip()
    style_profile = (payload.get("styleProfile") or "").strip()
    chat_history = _chat_history(payload.get("messages"), limit=12)

    if mode == "work":
        profile = {
            "모드": "직장/업무 작전 회의",
            "업무 관계": _label(payload.get("relation")),
            "회신 톤": _label(payload.get("contact")),
            "회신 목표": _label(payload.get("goal")),
            "상대 성향 메모": (payload.get("mbti") or "미입력").strip(),
            "상대 직급": payload.get("age") or "미입력",
            "관계 범위": payload.get("gender") or "미입력",
            "상대 직무": payload.get("job") or "미입력",
            "받은 업무 메시지": message or "미입력",
            "내 말투 분석": style_profile or "미입력",
            "현재 맥락 요약": context_summary or "미입력",
            "작전 회의 대화": chat_history,
        }
        return f"""
너는 모바일 앱 RE:BOUND의 업무 회신 상황실 진행자다.
목표는 사용자가 업무 답장을 더 정확히 만들 수 있도록 필요한 맥락을 짧게 캐는 것이다.

규칙:
- 한국어로 답한다.
- 한 번에 질문은 1~2개만 한다.
- 이미 충분한 맥락이 있으면 짧게 정리하고 "이 맥락으로 다시 짜도 됨"을 말한다.
- 책임 범위, 기한, 상대와의 관계, 사용자가 원하는 결과를 특히 확인한다.
- 법률/인사/계약처럼 민감한 상황은 단정하지 말고 문장을 보수적으로 잡으라고 알려준다.
- 답변은 80자 안팎으로 짧고 업무답게 한다.

입력:
{json.dumps(profile, ensure_ascii=False, indent=2)}

반드시 아래 JSON 형식만 출력한다. 마크다운, 설명 문장, 코드블록은 쓰지 마라.
{{
  "reply": "사용자에게 보낼 채팅 답변",
  "contextSummary": "지금까지 파악한 업무 맥락 요약 120자 내외",
  "ready": true 또는 false
}}
""".strip()

    profile = {
        "모드": "썸/연애 작전 회의",
        "관계": _label(payload.get("relation")),
        "연락 스타일": _label(payload.get("contact")),
        "내 목표": _label(payload.get("goal")),
        "상대 MBTI": (payload.get("mbti") or "미입력").strip().upper(),
        "상대 나이": payload.get("age") or "미입력",
        "상대 성별": payload.get("gender") or "미입력",
        "상대 직업": payload.get("job") or "미입력",
        "상대가 보낸 톡": message or "미입력",
        "내 말투 분석": style_profile or "미입력",
        "현재 맥락 요약": context_summary or "미입력",
        "작전 회의 대화": chat_history,
    }

    return f"""
너는 모바일 앱 RE:BOUND의 썸톡 작전 회의 진행자다.
목표는 사용자가 상대와의 앞뒤 상황을 털어놓게 해서 더 자연스럽고 덜 AI 같은 답장을 만들 맥락을 얻는 것이다.

캐릭터:
- 상담사처럼 길게 위로하지 않는다. 눈치 빠른 친구처럼 짧게 묻고 정리한다.
- 살짝 장난스럽고 통통 튀지만, 사용자를 조종적으로 보이게 만들면 실패다.

규칙:
- 한국어 카카오톡처럼 짧게 답한다.
- 한 번에 질문은 1~2개만 한다.
- 마지막 분위기, 사용자의 속마음, 밀고 싶은지 당기고 싶은지, 피하고 싶은 표현을 확인한다.
- 이미 충분한 맥락이 있으면 짧게 정리하고 "이 맥락으로 다시 짜도 됨"을 말한다.
- 답변은 90자 안팎으로 짧고 재밌게 한다.

입력:
{json.dumps(profile, ensure_ascii=False, indent=2)}

반드시 아래 JSON 형식만 출력한다. 마크다운, 설명 문장, 코드블록은 쓰지 마라.
{{
  "reply": "사용자에게 보낼 채팅 답변",
  "contextSummary": "지금까지 파악한 썸톡 맥락 요약 120자 내외",
  "ready": true 또는 false
}}
""".strip()


def _normalize_chat_result(data):
    if not isinstance(data, dict):
        raise ValueError("invalid chat result")
    reply = str(data.get("reply") or "").strip()
    if not reply:
        raise ValueError("empty chat reply")
    return {
        "reply": reply[:500],
        "contextSummary": str(data.get("contextSummary") or "")[:260],
        "ready": bool(data.get("ready")),
    }


def _generate_gemini_chat(payload):
    return _normalize_chat_result(
        _call_gemini_json(_build_chat_prompt(payload), max_tokens=700, temperature=0.86)
    )


def bootstrap(app, config):
    asset_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "public",
        "assets",
        "flirt-mascot.webp",
    )

    @app.flask.route("/assets/flirt-mascot.webp")
    def flirt_mascot():
        return send_file(asset_path, mimetype="image/webp", max_age=31536000)

    @app.flask.route("/api/replies", methods=["POST"])
    def api_replies():
        payload = request.get_json(silent=True) or {}
        try:
            return jsonify(_generate_gemini_replies(payload))
        except RuntimeError as error:
            if str(error) == "missing_api_key":
                return jsonify({"error": "missing_api_key"}), 503
            return jsonify({"error": "ai_runtime_error"}), 502
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError):
            return jsonify({"error": "ai_request_failed"}), 502
        except Exception:
            return jsonify({"error": "ai_response_invalid"}), 502

    @app.flask.route("/api/chat", methods=["POST"])
    def api_chat():
        payload = request.get_json(silent=True) or {}
        try:
            return jsonify(_generate_gemini_chat(payload))
        except RuntimeError as error:
            if str(error) == "missing_api_key":
                return jsonify({"error": "missing_api_key"}), 503
            return jsonify({"error": "ai_runtime_error"}), 502
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError):
            return jsonify({"error": "ai_request_failed"}), 502
        except Exception:
            return jsonify({"error": "ai_response_invalid"}), 502

    html = """<!doctype html>
<html lang="ko">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
    <title>RE:BOUND</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Bagel+Fat+One&family=Jua&display=swap" rel="stylesheet">
    <style>
        :root {
            --ink: #17130f;
            --paper: #fff6dc;
            --pink: #ff4f8b;
            --lime: #c7ff32;
            --blue: #254cff;
            --violet: #a66cff;
            --mint: #66ffd1;
            --orange: #ff7a1a;
            --cream: #fff8df;
            --line: 2px solid var(--ink);
        }

        * {
            box-sizing: border-box;
        }

        html,
        body {
            margin: 0;
            min-height: 100%;
            background:
                radial-gradient(circle at 18% 8%, rgba(199, 255, 50, .95) 0 10%, transparent 22%),
                radial-gradient(circle at 90% 18%, rgba(102, 255, 209, .88) 0 12%, transparent 24%),
                linear-gradient(135deg, #ff4f8b 0%, #ff7a1a 46%, #254cff 100%);
            color: var(--ink);
            font-family: "Jua", ui-rounded, "Arial Rounded MT Bold", "Apple SD Gothic Neo", "Malgun Gothic", system-ui, sans-serif;
            overflow-x: hidden;
            transition: background .35s ease;
        }

        html.work-mode,
        body.work-mode {
            background:
                radial-gradient(circle at 18% 12%, rgba(183, 255, 232, .82) 0 9%, transparent 24%),
                radial-gradient(circle at 86% 18%, rgba(214, 226, 244, .9) 0 13%, transparent 30%),
                radial-gradient(circle at 72% 86%, rgba(18, 24, 38, .2) 0 16%, transparent 34%),
                linear-gradient(135deg, #edf3fb 0%, #c8d5e6 48%, #8292aa 100%);
        }

        body {
            display: flex;
            justify-content: center;
        }

        button,
        input,
        textarea {
            font: inherit;
        }

        button {
            color: inherit;
            cursor: pointer;
            -webkit-tap-highlight-color: transparent;
        }

        .phone {
            position: relative;
            width: 100%;
            max-width: 430px;
            min-height: 100svh;
            background:
                linear-gradient(90deg, rgba(23, 19, 15, .07) 1px, transparent 1px),
                linear-gradient(180deg, rgba(23, 19, 15, .07) 1px, transparent 1px),
                linear-gradient(180deg, #fff0c8 0%, #ffd4e0 34%, #b9fff0 68%, #fff6dc 100%);
            background-size: 23px 23px, 23px 23px, auto;
            overflow: hidden;
            isolation: isolate;
            scrollbar-width: none;
            -ms-overflow-style: none;
        }

        .phone::-webkit-scrollbar {
            display: none;
            width: 0;
            height: 0;
        }

        .phone::before,
        .phone::after {
            content: "";
            position: absolute;
            z-index: 0;
            border: var(--line);
            transform: rotate(-9deg);
        }

        .phone::before {
            width: 260px;
            height: 260px;
            left: -95px;
            top: 82px;
            background: var(--lime);
            border-radius: 46% 54% 40% 60%;
            animation: blob 7s ease-in-out infinite;
        }

        .phone::after {
            width: 230px;
            height: 230px;
            right: -88px;
            bottom: 190px;
            background: var(--violet);
            border-radius: 54% 46% 60% 40%;
            animation: blob 8s ease-in-out infinite reverse;
        }

        .topbar {
            position: sticky;
            top: 0;
            left: 0;
            right: 0;
            z-index: 10;
            display: flex;
            align-items: center;
            gap: 10px;
            width: 100%;
            padding: max(14px, env(safe-area-inset-top)) 16px 10px;
            background: rgba(255, 246, 220, .96);
            border-bottom: var(--line);
            backdrop-filter: blur(14px);
        }

        .brand {
            display: grid;
            place-items: center;
            width: 46px;
            height: 46px;
            background: var(--blue);
            border: var(--line);
            border-radius: 50%;
            color: #fff;
            font-size: 22px;
            font-weight: 950;
            box-shadow: 4px 4px 0 var(--ink);
            transform: rotate(-8deg);
        }

        .brand,
        .brand-copy h1 {
            font-family: "Bagel Fat One", "Jua", ui-rounded, system-ui, sans-serif;
            font-weight: 400;
        }

        .brand-copy {
            min-width: 0;
            flex: 1;
        }

        .brand-copy h1 {
            margin: 0;
            font-size: 27px;
            line-height: .88;
            letter-spacing: 0;
        }

        .brand-copy p {
            margin: 5px 0 0;
            font-size: 12px;
            font-weight: 900;
        }

        .mode-switch {
            display: flex;
            flex: 0 0 auto;
            gap: 3px;
            padding: 3px;
            background: #fff;
            border: var(--line);
            border-radius: 999px;
            box-shadow: 3px 3px 0 var(--ink);
        }

        .mode-button {
            min-width: 48px;
            min-height: 31px;
            padding: 5px 8px 4px;
            border: 0;
            border-radius: 999px;
            background: transparent;
            font-size: 12px;
            font-weight: 950;
            line-height: 1;
        }

        .mode-button.is-active {
            background: var(--ink);
            color: #fff;
        }

        .signal {
            padding: 7px 9px 6px;
            background: var(--lime);
            border: var(--line);
            border-radius: 999px;
            font-size: 11px;
            font-weight: 950;
            box-shadow: 3px 3px 0 var(--ink);
            white-space: nowrap;
            animation: nudge 1.8s ease-in-out infinite;
        }

        .stage {
            position: relative;
            z-index: 1;
            padding: 18px 16px 120px;
        }

        .marquee {
            display: flex;
            width: calc(100% + 32px);
            margin: 0 -16px 15px;
            overflow: hidden;
            border-block: var(--line);
            background: var(--ink);
            color: #fff;
            font-size: 13px;
            font-weight: 950;
        }

        .marquee span {
            flex: 0 0 auto;
            padding: 9px 12px;
            animation: ticker 15s linear infinite;
            white-space: nowrap;
        }

        .hero {
            position: relative;
            min-height: 222px;
            margin-bottom: 8px;
        }

        .hero-title {
            position: relative;
            z-index: 2;
            margin: 0;
            max-width: 286px;
            font-family: "Jua", ui-rounded, system-ui, sans-serif;
            font-size: clamp(52px, 16vw, 74px);
            font-weight: 950;
            line-height: .88;
            letter-spacing: 0;
            text-transform: uppercase;
        }

        .hero-title span {
            display: inline-block;
            margin: 1px 0 2px;
            padding: 0 7px 3px;
            background: var(--lime);
            border: var(--line);
            box-shadow: 3px 3px 0 var(--ink);
            transform: rotate(-3deg);
        }

        .mascot {
            position: absolute;
            right: -30px;
            top: 28px;
            z-index: 1;
            width: min(52vw, 214px);
            aspect-ratio: 1;
            object-fit: cover;
            border: var(--line);
            border-radius: 8px;
            box-shadow: 8px 8px 0 var(--ink);
            transform: rotate(8deg);
            animation: floaty 4.2s ease-in-out infinite;
        }

        .mascot-scene {
            position: absolute;
            right: -30px;
            top: 28px;
            z-index: 1;
            width: min(52vw, 214px);
            aspect-ratio: 1;
            border: 4px solid var(--ink);
            border-radius: 8px;
            background: #4f68b3;
            box-shadow: 8px 8px 0 var(--ink);
            transform: rotate(8deg);
            overflow: visible;
        }

        .date-mascot {
            position: absolute;
            inset: 0;
            overflow: visible;
            border-radius: 5px;
        }

        .date-mascot::before {
            content: "";
            position: absolute;
            left: 1px;
            top: 19px;
            z-index: 1;
            width: 207px;
            height: 170px;
            background: #fff3ad;
            border: 5px solid var(--orange);
            clip-path: polygon(50% 0, 59% 31%, 98% 17%, 73% 48%, 99% 73%, 63% 65%, 56% 100%, 45% 67%, 7% 88%, 28% 55%, 0 33%, 37% 38%);
            transform: rotate(-10deg) scale(.91);
            animation: starPulse 5.8s ease-in-out infinite;
        }

        .date-mascot::after {
            content: "";
            position: absolute;
            left: 55px;
            bottom: 14px;
            z-index: 2;
            width: 112px;
            height: 24px;
            background: #ff7a1a;
            border: 4px solid var(--ink);
            border-radius: 50%;
            transform: rotate(-3deg);
            opacity: .9;
        }

        .date-face {
            position: absolute;
            left: 39px;
            top: 72px;
            z-index: 5;
            width: 142px;
            height: 108px;
            background:
                radial-gradient(circle at 76% 72%, rgba(255, 246, 220, .48) 0 8px, transparent 9px),
                radial-gradient(circle at 23% 72%, rgba(255, 246, 220, .42) 0 8px, transparent 9px),
                #ff4f8b;
            border: 5px solid var(--ink);
            border-radius: 47% 51% 48% 52% / 46% 48% 54% 52%;
            box-shadow: inset -10px -10px 0 rgba(77, 21, 92, .18);
            transform-origin: 52% 78%;
            animation: dateFaceAct 6.2s ease-in-out infinite;
        }

        .date-face::before {
            content: "";
            position: absolute;
            left: 21px;
            top: 74px;
            width: 8px;
            height: 8px;
            background: #fff6dc;
            border: 0;
            border-radius: 50%;
            box-shadow:
                9px 7px 0 -2px #fff6dc,
                84px -2px 0 #fff6dc,
                75px 6px 0 -2px #fff6dc;
            transform: rotate(-4deg);
        }

        .date-face::after {
            display: none;
        }

        .date-tail {
            position: absolute;
            right: 7px;
            top: 124px;
            z-index: 4;
            width: 70px;
            height: 57px;
            background: transparent;
            border: 0;
            border-right: 6px solid var(--ink);
            border-bottom: 6px solid var(--ink);
            border-radius: 0 0 80% 0;
            box-shadow: none;
            transform: rotate(-26deg);
        }

        .date-tail::before {
            content: "";
            position: absolute;
            right: -20px;
            top: -6px;
            width: 27px;
            height: 24px;
            background: #ff4f8b;
            border: 5px solid var(--ink);
            border-radius: 48% 52% 46% 54%;
            clip-path: polygon(0 0, 100% 50%, 0 100%);
            transform: rotate(-11deg);
        }

        .date-horn {
            position: absolute;
            z-index: 9;
            width: 34px;
            height: 38px;
            background: #fff6dc;
            border: 5px solid var(--ink);
            border-radius: 55% 45% 15% 15%;
            clip-path: polygon(50% 0, 100% 100%, 0 100%);
        }

        .date-horn::after {
            display: none;
        }

        .date-horn.left {
            left: 51px;
            top: 43px;
            transform: rotate(-17deg);
        }

        .date-horn.right {
            right: 23px;
            top: 44px;
            transform: rotate(17deg) scaleX(-1);
        }

        .date-cap {
            position: absolute;
            left: 78px;
            top: 64px;
            z-index: 7;
            width: 66px;
            height: 24px;
            background: #17130f;
            border: 0;
            border-radius: 999px 999px 14px 14px;
            box-shadow: none;
            transform: rotate(-4deg);
            overflow: visible;
            animation: dateCapAct 6.2s ease-in-out infinite;
        }

        .date-cap::before {
            display: none;
        }

        .date-cap::after {
            display: none;
        }

        .date-brim {
            position: absolute;
            left: 57px;
            top: 160px;
            z-index: 4;
            width: 112px;
            height: 25px;
            background: var(--orange);
            border: 5px solid var(--ink);
            border-radius: 50%;
            transform: rotate(-4deg);
            box-shadow: inset 0 -6px 0 rgba(107, 0, 8, .1);
            animation: dateBrimAct 6.2s ease-in-out infinite;
        }

        .date-glasses {
            position: absolute;
            left: 62px;
            top: 101px;
            z-index: 11;
            width: 88px;
            height: 35px;
            transform: rotate(2deg);
            animation: dateGlasses 6.2s ease-in-out infinite;
        }

        .date-glasses::before,
        .date-glasses::after {
            content: "";
            position: absolute;
            top: 1px;
            width: 37px;
            height: 29px;
            z-index: 1;
            background: rgba(255, 255, 255, .48);
            border: 5px solid var(--ink);
            border-radius: 49% 54% 48% 52%;
            box-shadow: inset 4px 4px 0 rgba(255, 255, 255, .34);
        }

        .date-glasses::before {
            left: 0;
        }

        .date-glasses::after {
            right: 0;
        }

        .date-bridge {
            position: absolute;
            left: 38px;
            top: 15px;
            z-index: 3;
            width: 13px;
            height: 5px;
            background: var(--ink);
            border-radius: 999px;
        }

        .date-eye {
            position: absolute;
            top: 13px;
            z-index: 2;
            width: 11px;
            height: 13px;
            background: var(--ink);
            border-radius: 60% 50% 55% 45%;
            transform-origin: 50% 50%;
        }

        .date-eye.left {
            left: 15px;
            animation: dateEyeDot 6.2s ease-in-out infinite;
        }

        .date-eye.right {
            right: 15px;
        }

        .date-eye::before,
        .date-eye::after {
            content: "";
            position: absolute;
            width: 4px;
            height: 14px;
            background: var(--ink);
            border-radius: 999px;
            opacity: .95;
        }

        .date-eye::before {
            left: -11px;
            top: -11px;
            transform: rotate(-35deg);
        }

        .date-eye::after {
            right: -11px;
            top: -11px;
            transform: rotate(35deg);
        }

        .date-wink-line {
            position: absolute;
            left: 9px;
            top: 12px;
            z-index: 5;
            width: 20px;
            height: 9px;
            opacity: 0;
            border-bottom: 5px solid var(--ink);
            border-radius: 0 0 999px 999px;
            transform: rotate(-7deg) scaleX(.65);
            transform-origin: 50% 50%;
            animation: dateWinkLine 6.2s ease-in-out infinite;
        }

        .date-wink-line::before,
        .date-wink-line::after {
            display: none;
        }

        .date-glint {
            position: absolute;
            left: 23px;
            top: 31px;
            z-index: 12;
            width: 18px;
            height: 18px;
            background: #fff6dc;
            border: 4px solid var(--orange);
            clip-path: polygon(50% 0, 62% 38%, 100% 50%, 62% 62%, 50% 100%, 38% 62%, 0 50%, 38% 38%);
            transform: rotate(-17deg) scale(.75);
            transform-origin: 50% 50%;
            animation: sparkleBlink 6.2s ease-in-out infinite;
        }

        .date-mouth {
            position: absolute;
            left: 96px;
            top: 142px;
            z-index: 12;
            width: 30px;
            height: 15px;
            border-bottom: 5px solid var(--ink);
            border-right: 5px solid var(--ink);
            border-radius: 0 0 50% 50%;
            transform: rotate(-10deg);
        }

        .date-tongue {
            position: absolute;
            left: 90px;
            top: 135px;
            z-index: 12;
            width: 14px;
            height: 14px;
            background: #fff;
            border: 4px solid var(--ink);
            border-radius: 50%;
            transform: rotate(-14deg) scale(.2);
            transform-origin: 50% 50%;
            animation: dateKissFace 6.2s ease-in-out infinite;
        }

        .date-pop-kiss {
            position: absolute;
            z-index: 9;
            pointer-events: none;
        }

        .date-pop-kiss {
            left: 146px;
            top: 121px;
            display: grid;
            place-items: center;
            width: 34px;
            height: 34px;
            opacity: 0;
            transform: translate(0, 0) rotate(-8deg) scale(.45);
            transform-origin: 50% 62%;
            animation: dateKissPop 6.2s ease-in-out infinite;
        }

        .date-pop-kiss::before {
            content: "♥";
            color: #ff2d75;
            font-family: "Arial Rounded MT Bold", "Jua", ui-rounded, system-ui, sans-serif;
            font-size: 34px;
            line-height: 1;
            -webkit-text-stroke: 2px var(--ink);
            text-shadow: 2px 2px 0 var(--ink);
        }

        .date-pop-kiss::after {
            display: none;
        }

        .office-mascot {
            position: absolute;
            right: -4px;
            top: 10px;
            z-index: 1;
            display: none;
            width: 178px;
            height: 188px;
            background: #f8fbff;
            border: var(--line);
            border-radius: 12px;
            box-shadow: 6px 6px 0 rgba(18, 24, 38, .24);
            overflow: hidden;
        }

        .office-mascot::before {
            content: "";
            position: absolute;
            inset: 0;
            background:
                linear-gradient(180deg, #e8f1ff 0 31px, transparent 31px),
                linear-gradient(90deg, rgba(18, 24, 38, .08) 1px, transparent 1px),
                linear-gradient(180deg, rgba(18, 24, 38, .08) 1px, transparent 1px);
            background-size: auto, 18px 18px, 18px 18px;
        }

        .office-mascot::after {
            content: "";
            position: absolute;
            left: 13px;
            right: 13px;
            bottom: 13px;
            height: 38px;
            background: #ffffff;
            border: var(--line);
            border-radius: 6px;
            box-shadow: 3px 3px 0 rgba(18, 24, 38, .22);
        }

        .office-worker {
            position: absolute;
            left: 41px;
            top: 30px;
            width: 92px;
            height: 128px;
            z-index: 3;
            transform-origin: 50% 76%;
            animation: officeFocus 6.2s ease-in-out infinite;
        }

        .office-head {
            position: absolute;
            left: 19px;
            top: 0;
            width: 54px;
            height: 58px;
            background: #ffd8ba;
            border: var(--line);
            border-radius: 18px 18px 20px 20px;
            overflow: hidden;
        }

        .office-hair {
            position: absolute;
            left: -4px;
            top: -8px;
            width: 64px;
            height: 25px;
            background: #243047;
            border-bottom: var(--line);
            border-radius: 18px 18px 9px 9px;
        }

        .office-glasses {
            position: absolute;
            left: 9px;
            top: 25px;
            width: 36px;
            height: 12px;
            border-top: 3px solid var(--ink);
            transform-origin: 50% 50%;
            animation: glassesAdjust 6.2s ease-in-out infinite;
        }

        .office-glasses::before,
        .office-glasses::after {
            content: "";
            position: absolute;
            top: -6px;
            width: 13px;
            height: 10px;
            border: 2px solid var(--ink);
            border-radius: 4px;
            background: rgba(255, 255, 255, .38);
        }

        .office-glasses::before {
            left: 0;
        }

        .office-glasses::after {
            right: 0;
        }

        .office-mouth {
            position: absolute;
            left: 22px;
            top: 42px;
            width: 12px;
            height: 5px;
            border-bottom: 3px solid var(--ink);
            border-radius: 50%;
        }

        .office-body {
            position: absolute;
            left: 8px;
            top: 54px;
            width: 76px;
            height: 80px;
            background: #26344f;
            border: var(--line);
            border-radius: 14px 14px 8px 8px;
        }

        .office-shirt {
            position: absolute;
            left: 20px;
            top: -2px;
            width: 36px;
            height: 39px;
            background: #ffffff;
            border-inline: var(--line);
            clip-path: polygon(0 0, 100% 0, 82% 100%, 18% 100%);
        }

        .office-tie {
            position: absolute;
            left: 34px;
            top: 5px;
            width: 9px;
            height: 45px;
            background: #1f8fff;
            border: 2px solid var(--ink);
            clip-path: polygon(50% 0, 100% 20%, 72% 100%, 28% 100%, 0 20%);
        }

        .office-badge {
            position: absolute;
            right: 7px;
            top: 23px;
            width: 15px;
            height: 20px;
            background: #dfff4f;
            border: 2px solid var(--ink);
            border-radius: 3px;
        }

        .office-hand {
            position: absolute;
            left: 63px;
            top: 37px;
            z-index: 6;
            width: 34px;
            height: 54px;
            background: transparent;
            border: 0;
            transform-origin: 8px 50px;
            transform: translate(8px, 12px) rotate(8deg) scale(.92);
            animation: handAdjust 6.2s ease-in-out infinite;
        }

        .office-hand::before {
            content: "";
            position: absolute;
            left: 5px;
            bottom: 1px;
            width: 13px;
            height: 43px;
            background: #26344f;
            border: 2px solid var(--ink);
            border-radius: 999px;
            transform: rotate(18deg);
            transform-origin: 50% 100%;
        }

        .office-hand::after {
            content: "";
            position: absolute;
            left: 12px;
            top: -2px;
            width: 17px;
            height: 19px;
            background: #ffd8ba;
            border: 2px solid var(--ink);
            border-radius: 50% 50% 46% 46%;
            transform: rotate(-10deg);
        }

        .office-paper {
            position: absolute;
            right: 16px;
            bottom: 51px;
            z-index: 3;
            width: 50px;
            height: 66px;
            background: #ffffff;
            border: var(--line);
            border-radius: 4px;
            box-shadow: 3px 3px 0 rgba(18, 24, 38, .14);
            transform: translateY(62px) rotate(7deg);
            transform-origin: 50% 100%;
            animation: paperLift 6.2s ease-in-out infinite;
        }

        .office-paper::before {
            content: "";
            position: absolute;
            left: 8px;
            top: 12px;
            width: 30px;
            height: 3px;
            background: #aeb9ca;
            box-shadow:
                0 10px 0 #c8d1df,
                0 20px 0 #c8d1df,
                0 30px 0 #c8d1df;
        }

        .office-paper::after {
            content: "";
            position: absolute;
            right: -2px;
            top: -2px;
            width: 14px;
            height: 14px;
            background: #e8f1ff;
            border-left: 2px solid var(--ink);
            border-bottom: 2px solid var(--ink);
            border-radius: 0 2px 0 4px;
        }

        .office-laptop {
            position: absolute;
            left: 31px;
            bottom: 20px;
            z-index: 4;
            width: 116px;
            height: 50px;
            background: #dfe7f5;
            border: var(--line);
            border-radius: 6px 6px 3px 3px;
            box-shadow: 2px 2px 0 rgba(18, 24, 38, .18);
        }

        .office-laptop::before {
            content: "";
            position: absolute;
            left: 49px;
            top: 15px;
            width: 16px;
            height: 16px;
            background: #9ff4df;
            border: 2px solid var(--ink);
            border-radius: 50%;
        }

        .office-laptop::after {
            content: "";
            position: absolute;
            left: -8px;
            right: -8px;
            bottom: -9px;
            height: 10px;
            background: #121826;
            border: 2px solid var(--ink);
            border-radius: 0 0 8px 8px;
        }

        .stamp {
            position: absolute;
            z-index: 3;
            display: grid;
            place-items: center;
            width: 96px;
            height: 96px;
            right: 130px;
            bottom: 8px;
            background: var(--pink);
            border: var(--line);
            border-radius: 50%;
            color: #fff;
            font-family: "Jua", ui-rounded, system-ui, sans-serif;
            font-size: 18px;
            font-weight: 950;
            line-height: .88;
            text-align: center;
            text-shadow: 1px 1px 0 var(--ink);
            box-shadow: 5px 5px 0 var(--ink);
            transform: rotate(-15deg);
        }

        .panel {
            position: relative;
            z-index: 1;
            margin-top: 14px;
            padding: 13px;
            background: #fffdf4;
            border: var(--line);
            border-radius: 8px;
            box-shadow: 7px 7px 0 var(--ink);
        }

        .panel.is-menu-open {
            z-index: 60;
        }

        .panel:nth-of-type(2n) {
            transform: rotate(.5deg);
        }

        .panel:nth-of-type(3n) {
            transform: rotate(-.4deg);
        }

        .step {
            position: absolute;
            left: 12px;
            top: -15px;
            padding: 5px 8px;
            background: var(--orange);
            border: var(--line);
            border-radius: 999px;
            color: #fff;
            font-size: 12px;
            font-weight: 950;
            transform: rotate(-3deg);
        }

        .step.blue {
            background: var(--blue);
        }

        .step.pink {
            background: var(--pink);
        }

        .step.mint {
            background: var(--mint);
            color: var(--ink);
        }

        .panel-title {
            display: flex;
            align-items: center;
            gap: 8px;
            margin: 9px 0 10px;
            font-size: 13px;
            font-weight: 950;
            text-transform: uppercase;
        }

        .panel-title::after {
            content: "";
            flex: 1;
            height: 2px;
            background: var(--ink);
        }

        .hint {
            margin: -2px 0 10px;
            font-size: 12px;
            line-height: 1.25;
            font-weight: 850;
        }

        .chips {
            display: flex;
            gap: 8px;
            overflow-x: auto;
            padding: 2px 2px 8px;
            scrollbar-width: none;
        }

        .chips.wrap {
            flex-wrap: wrap;
            overflow-x: visible;
            padding-bottom: 2px;
        }

        .chips::-webkit-scrollbar {
            display: none;
        }

        .chip {
            flex: 0 0 auto;
            padding: 10px 12px;
            border: var(--line);
            border-radius: 999px;
            background: #fff;
            font-size: 14px;
            font-weight: 950;
            box-shadow: 3px 3px 0 var(--ink);
            transition: transform .16s ease, background .16s ease, box-shadow .16s ease;
        }

        .chip.is-active {
            background: var(--blue);
            color: #fff;
            transform: translate(-1px, -2px) rotate(-2deg);
        }

        .chips[data-group="relation"] .chip.is-active {
            background: var(--orange);
        }

        .chips[data-group="goal"] .chip.is-active {
            background: var(--pink);
        }

        .profile-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 10px;
        }

        .field {
            position: relative;
        }

        .field.wide {
            grid-column: 1 / -1;
        }

        .field label {
            display: block;
            margin: 0 0 5px;
            font-size: 11px;
            font-weight: 950;
            text-transform: uppercase;
        }

        input,
        textarea {
            width: 100%;
            border: var(--line);
            border-radius: 8px;
            background: #f2ff77;
            color: var(--ink);
            font-weight: 900;
            outline: none;
            box-shadow: inset 3px 3px 0 rgba(23, 19, 15, .15);
        }

        input {
            min-height: 46px;
            padding: 10px 11px;
            font-size: 16px;
        }

        .select-wrap {
            position: relative;
            width: 100%;
            min-height: 48px;
            background: #b9fff0;
            border: var(--line);
            border-radius: 8px;
            box-shadow: 4px 4px 0 var(--ink);
            transition: transform .16s ease, box-shadow .16s ease;
        }

        .select-wrap::after {
            content: "";
            position: absolute;
            right: 15px;
            top: 50%;
            width: 9px;
            height: 9px;
            border-right: 3px solid var(--ink);
            border-bottom: 3px solid var(--ink);
            transform: translateY(-68%) rotate(45deg);
            pointer-events: none;
        }

        .select-wrap:focus-within {
            transform: translate(-1px, -2px) rotate(-1deg);
            box-shadow: 6px 6px 0 var(--ink);
        }

        .field:nth-child(3) .select-wrap {
            background: #d9c0ff;
        }

        .select-wrap.is-open {
            z-index: 20;
            transform: translate(-1px, -2px) rotate(-1deg);
            box-shadow: 6px 6px 0 var(--ink);
        }

        .select-button {
            position: relative;
            width: 100%;
            min-height: 46px;
            padding: 10px 36px 10px 11px;
            border: 0;
            border-radius: 6px;
            background: transparent;
            color: var(--ink);
            font-size: 20px;
            font-weight: 950;
            line-height: 1.05;
            text-align: left;
            outline: none;
        }

        .select-menu {
            position: absolute;
            z-index: 70;
            left: -2px;
            right: -2px;
            top: calc(100% + 8px);
            display: none;
            gap: 7px;
            padding: 8px;
            max-height: min(310px, 52svh);
            overflow-y: auto;
            overscroll-behavior: contain;
            background: rgba(255, 253, 244, .96);
            border: var(--line);
            border-radius: 12px;
            box-shadow: 7px 7px 0 var(--ink);
            backdrop-filter: blur(12px);
            scrollbar-width: none;
        }

        .select-menu::-webkit-scrollbar {
            display: none;
        }

        .select-wrap.is-open .select-menu {
            display: grid;
        }

        .select-option {
            position: relative;
            min-height: 40px;
            padding: 8px 12px;
            border: var(--line);
            border-radius: 999px;
            background: #fff;
            color: var(--ink);
            font-size: 16px;
            font-weight: 950;
            line-height: 1.05;
            text-align: left;
            box-shadow: 2px 2px 0 var(--ink);
        }

        .select-option.is-selected {
            background: var(--blue);
            color: #fff;
            transform: rotate(-1deg);
        }

        textarea {
            min-height: 122px;
            resize: none;
            padding: 14px;
            font-size: 20px;
            line-height: 1.2;
        }

        .draft-input {
            min-height: 82px;
            margin-bottom: 4px;
            background: #fffdf4;
            font-size: 17px;
        }

        .style-panel {
            background: #e4c6ff;
        }

        .voice-prompt-card {
            padding: 11px;
            background: #fff6dc;
            border: var(--line);
            border-radius: 8px;
            box-shadow: 4px 4px 0 var(--ink);
        }

        .voice-prompt-card span {
            display: inline-block;
            margin-bottom: 7px;
            padding: 4px 8px;
            background: var(--orange);
            border: 2px solid var(--ink);
            border-radius: 999px;
            color: #fff;
            font-size: 11px;
            font-weight: 950;
        }

        .voice-prompt-card strong {
            display: block;
            margin-bottom: 6px;
            font-size: 11px;
            font-weight: 950;
        }

        .voice-prompt-card p {
            margin: 0;
            font-size: 18px;
            line-height: 1.2;
            font-weight: 950;
            word-break: keep-all;
        }

        .style-input {
            min-height: 72px;
            background: #fffdf4;
            font-size: 17px;
        }

        .style-storage {
            display: none;
        }

        .style-actions {
            display: grid;
            grid-template-columns: 1fr 1fr 74px;
            gap: 9px;
            margin-top: 10px;
        }

        .style-next,
        .style-sync,
        .style-clear {
            min-height: 46px;
            border: var(--line);
            border-radius: 8px;
            font-weight: 950;
            box-shadow: 4px 4px 0 var(--ink);
        }

        .style-next {
            background: var(--orange);
            color: #fff;
        }

        .style-sync {
            background: var(--lime);
        }

        .style-clear {
            background: #fff;
        }

        .style-summary {
            margin-top: 11px;
            padding: 11px;
            background: #b9fff0;
            border: var(--line);
            border-radius: 8px;
            box-shadow: 4px 4px 0 var(--ink);
        }

        .style-summary.is-empty {
            display: none;
        }

        .style-summary strong {
            display: inline-block;
            margin-bottom: 6px;
            padding: 4px 8px;
            background: var(--ink);
            border-radius: 999px;
            color: #fff;
            font-size: 11px;
            font-weight: 950;
        }

        .style-summary p {
            margin: 0;
            font-size: 13px;
            line-height: 1.24;
            font-weight: 900;
            word-break: keep-all;
        }

        .style-tags {
            display: flex;
            flex-wrap: wrap;
            gap: 6px;
            margin-top: 9px;
        }

        .style-tag {
            padding: 5px 8px;
            background: #fff;
            border: 2px solid var(--ink);
            border-radius: 999px;
            font-size: 11px;
            font-weight: 950;
        }

        .style-answer-list {
            display: flex;
            flex-wrap: wrap;
            gap: 6px;
            min-height: 0;
            margin-top: 9px;
        }

        .style-answer-pill {
            max-width: 100%;
            padding: 5px 8px;
            background: #fff;
            border: 2px solid var(--ink);
            border-radius: 999px;
            font-size: 11px;
            font-weight: 950;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }

        input::placeholder,
        textarea::placeholder {
            color: rgba(23, 19, 15, .46);
        }

        .message-panel {
            background: #ffe3ed;
        }

        .actions {
            display: grid;
            grid-template-columns: 1fr 54px;
            gap: 10px;
            margin-top: 12px;
        }

        .roll,
        .dice {
            min-height: 56px;
            border: var(--line);
            border-radius: 8px;
            font-weight: 950;
            box-shadow: 5px 5px 0 var(--ink);
            transition: transform .15s ease, box-shadow .15s ease;
        }

        .roll {
            background: var(--pink);
            color: #fff;
            font-size: 18px;
        }

        .roll.is-loading {
            background: var(--blue);
            color: #fff;
        }

        .dice {
            background: var(--mint);
            font-size: 25px;
        }

        .roll:active,
        .dice:active,
        .reply:active {
            transform: translate(4px, 4px);
            box-shadow: 1px 1px 0 var(--ink);
        }

        .brief {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 8px;
            margin: 18px 0 12px;
        }

        .brief div {
            min-height: 52px;
            display: grid;
            place-items: center;
            padding: 9px 8px;
            background: #fff;
            border: var(--line);
            border-radius: 8px;
            font-size: 11px;
            font-weight: 950;
            line-height: 1.15;
            text-align: center;
            box-shadow: 3px 3px 0 var(--ink);
        }

        .brief div:nth-child(2) {
            background: var(--lime);
        }

        .brief div:nth-child(3) {
            background: var(--violet);
            color: #fff;
        }

        .result-tools {
            display: grid;
            gap: 10px;
            margin: 0 0 13px;
            scroll-margin-top: 84px;
        }

        .result-tools.is-empty,
        .compare-view.is-empty,
        .is-hidden {
            display: none !important;
        }

        .warning-card {
            position: relative;
            padding: 13px 14px;
            background: #fff;
            border: var(--line);
            border-radius: 8px;
            box-shadow: 5px 5px 0 var(--ink);
        }

        .warning-card.ok {
            background: #b9fff0;
        }

        .warning-card.watch {
            background: #fff071;
        }

        .warning-card.danger {
            background: #ff8bab;
        }

        .warning-card strong {
            display: inline-block;
            margin-bottom: 5px;
            padding: 4px 8px;
            background: var(--ink);
            border-radius: 999px;
            color: #fff;
            font-size: 11px;
            font-weight: 950;
        }

        .warning-card p {
            margin: 0;
            font-size: 14px;
            line-height: 1.24;
            font-weight: 900;
            word-break: keep-all;
        }

        .result-panel {
            padding: 12px;
            background: #fffdf4;
            border: var(--line);
            border-radius: 8px;
            box-shadow: 4px 4px 0 var(--ink);
        }

        .result-panel .panel-title {
            margin-top: 0;
            font-size: 12px;
        }

        .conference-toggle {
            width: 100%;
            min-height: 46px;
            margin-top: 7px;
            border: var(--line);
            border-radius: 8px;
            background: var(--orange);
            color: #fff;
            font-size: 14px;
            font-weight: 950;
            box-shadow: 4px 4px 0 var(--ink);
        }

        .conference-panel {
            display: grid;
            gap: 10px;
            margin: 0 0 13px;
            padding: 13px;
            background: #fffdf4;
            border: var(--line);
            border-radius: 8px;
            box-shadow: 6px 6px 0 var(--ink);
            scroll-margin-top: 84px;
        }

        .conference-panel.is-empty {
            display: none;
        }

        .conference-head {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 8px;
        }

        .conference-head .panel-title {
            flex: 1;
            margin: 0;
        }

        .conference-close {
            width: 34px;
            height: 34px;
            border: var(--line);
            border-radius: 50%;
            background: #fff;
            font-size: 18px;
            font-weight: 950;
            line-height: 1;
            box-shadow: 2px 2px 0 var(--ink);
        }

        .conference-hint {
            margin: -3px 0 0;
            font-size: 12px;
            line-height: 1.25;
            font-weight: 900;
        }

        .chat-log {
            display: grid;
            gap: 8px;
            max-height: 260px;
            overflow-y: auto;
            padding: 3px 2px 8px;
            scrollbar-width: none;
        }

        .chat-log::-webkit-scrollbar {
            display: none;
        }

        .chat-bubble {
            width: min(88%, 330px);
            padding: 10px 11px;
            border: var(--line);
            border-radius: 8px;
            background: #fff;
            box-shadow: 3px 3px 0 var(--ink);
            font-size: 14px;
            font-weight: 900;
            line-height: 1.25;
            word-break: keep-all;
        }

        .chat-bubble.user {
            justify-self: end;
            background: var(--pink);
            color: #fff;
            transform: rotate(1deg);
        }

        .chat-bubble.assistant {
            justify-self: start;
            background: #b9fff0;
            transform: rotate(-.7deg);
        }

        .context-chip {
            display: none;
            padding: 8px 10px;
            background: #e4c6ff;
            border: var(--line);
            border-radius: 8px;
            font-size: 12px;
            font-weight: 900;
            line-height: 1.22;
        }

        .context-chip.is-on {
            display: block;
        }

        .chat-compose {
            display: grid;
            grid-template-columns: 1fr 50px;
            gap: 8px;
        }

        .chat-input {
            min-height: 50px;
            max-height: 118px;
            background: #fff;
            font-size: 15px;
        }

        .chat-send {
            min-height: 50px;
            border: var(--line);
            border-radius: 8px;
            background: var(--blue);
            color: #fff;
            font-size: 18px;
            font-weight: 950;
            box-shadow: 4px 4px 0 var(--ink);
        }

        .context-regenerate {
            min-height: 48px;
            border: var(--line);
            border-radius: 8px;
            background: var(--lime);
            font-size: 14px;
            font-weight: 950;
            box-shadow: 4px 4px 0 var(--ink);
        }

        .tone-options,
        .view-toggle {
            display: flex;
            gap: 8px;
            overflow-x: auto;
            padding: 2px 2px 7px;
            scrollbar-width: none;
        }

        .tone-options::-webkit-scrollbar,
        .view-toggle::-webkit-scrollbar {
            display: none;
        }

        .tone-chip,
        .view-button {
            flex: 0 0 auto;
            min-height: 40px;
            padding: 8px 12px;
            border: var(--line);
            border-radius: 999px;
            background: #fff;
            font-size: 13px;
            font-weight: 950;
            box-shadow: 3px 3px 0 var(--ink);
        }

        .tone-chip.is-busy {
            opacity: .62;
        }

        .view-button.is-active {
            background: var(--pink);
            color: #fff;
            transform: translate(-1px, -1px) rotate(-2deg);
        }

        .compare-view {
            display: grid;
            gap: 10px;
            margin-bottom: 12px;
            scroll-margin-top: 84px;
        }

        .compare-card {
            padding: 12px;
            background: #fff;
            border: var(--line);
            border-radius: 8px;
            box-shadow: 4px 4px 0 var(--ink);
            color: inherit;
            text-align: left;
        }

        .compare-card:nth-child(even) {
            background: #d9c0ff;
        }

        .compare-card.is-copied {
            transform: translate(2px, 2px);
            box-shadow: 2px 2px 0 var(--ink);
        }

        .compare-card strong {
            display: inline-block;
            margin-bottom: 6px;
            padding: 4px 8px;
            background: var(--ink);
            border-radius: 999px;
            color: #fff;
            font-size: 11px;
            font-weight: 950;
        }

        .compare-card p {
            margin: 0 0 8px;
            font-size: 15px;
            line-height: 1.25;
            font-weight: 900;
            word-break: keep-all;
        }

        .compare-card small {
            display: block;
            font-size: 11px;
            line-height: 1.2;
            font-weight: 900;
            opacity: .72;
        }

        .replies {
            display: grid;
            gap: 12px;
            scroll-margin-top: 84px;
        }

        .replies.is-empty {
            display: none;
        }

        .reply {
            position: relative;
            width: min(94%, 370px);
            padding: 15px 16px 16px;
            border: var(--line);
            border-radius: 8px;
            background: #fff;
            box-shadow: 6px 6px 0 var(--ink);
            text-align: left;
            transition: transform .18s ease, box-shadow .18s ease;
        }

        .reply:nth-child(even) {
            justify-self: end;
            background: #d9c0ff;
            transform: rotate(1.4deg);
        }

        .reply:nth-child(odd) {
            transform: rotate(-1.1deg);
        }

        .reply strong {
            display: inline-block;
            margin-bottom: 8px;
            padding: 5px 8px;
            background: var(--ink);
            border-radius: 999px;
            color: #fff;
            font-size: 11px;
            font-weight: 950;
        }

        .reply p {
            margin: 0;
            font-size: 18px;
            line-height: 1.28;
            font-weight: 850;
            word-break: keep-all;
        }

        .reply small {
            display: block;
            margin-top: 10px;
            font-size: 11px;
            line-height: 1.2;
            font-weight: 900;
            opacity: .74;
        }

        .reply-next {
            margin-top: 10px;
            padding: 9px 10px;
            background: #fff6dc;
            border: 2px solid var(--ink);
            border-radius: 8px;
            font-size: 12px;
            font-weight: 900;
            line-height: 1.2;
        }

        .result-tools,
        .warning-card,
        .result-panel,
        .compare-view,
        .compare-card,
        .replies,
        .reply {
            min-width: 0;
            max-width: 100%;
        }

        .warning-card,
        .compare-card,
        .reply {
            white-space: normal;
        }

        .warning-card p,
        .compare-card p,
        .compare-card small,
        .reply p,
        .reply small,
        .reply-next,
        .context-chip,
        .chat-bubble {
            max-width: 100%;
            white-space: normal;
            word-break: normal;
            overflow-wrap: anywhere;
            line-break: anywhere;
        }

        .reply-copy-state {
            position: absolute;
            right: 10px;
            top: 10px;
            display: none;
            padding: 4px 7px;
            background: var(--lime);
            border: 2px solid var(--ink);
            border-radius: 999px;
            font-size: 10px;
            font-weight: 950;
        }

        .reply.is-copied .reply-copy-state {
            display: inline-block;
        }

        .toast {
            position: fixed;
            left: 50%;
            bottom: calc(20px + env(safe-area-inset-bottom));
            z-index: 30;
            width: min(360px, calc(100vw - 32px));
            padding: 13px 16px;
            background: var(--ink);
            border: 2px solid #fff;
            border-radius: 999px;
            color: #fff;
            font-size: 14px;
            font-weight: 950;
            text-align: center;
            transform: translate(-50%, 120px);
            transition: transform .22s cubic-bezier(.2, 1.4, .4, 1);
        }

        .toast.is-on {
            transform: translate(-50%, 0);
        }

        .phone.work-mode {
            --ink: #121826;
            --paper: #f8fbff;
            --pink: #2762ff;
            --lime: #d9ffe8;
            --blue: #17223b;
            --violet: #e7edff;
            --mint: #9ff4df;
            --orange: #f4b740;
            background:
                linear-gradient(90deg, rgba(18, 24, 38, .045) 1px, transparent 1px),
                linear-gradient(180deg, rgba(18, 24, 38, .045) 1px, transparent 1px),
                linear-gradient(180deg, #f7f9fd 0%, #edf3fb 52%, #f8fbff 100%);
            background-size: 20px 20px, 20px 20px, auto;
        }

        .phone.work-mode::before {
            width: 270px;
            height: 160px;
            left: -116px;
            top: 118px;
            background:
                linear-gradient(180deg, #dfe7f5 0 30px, #ffffff 30px);
            border-radius: 10px;
            box-shadow: 6px 6px 0 rgba(18, 24, 38, .14);
            animation: none;
            transform: rotate(-5deg);
        }

        .phone.work-mode::after {
            width: 210px;
            height: 260px;
            right: -104px;
            bottom: 196px;
            background:
                linear-gradient(180deg, #fff 0 36px, #eff5ff 36px);
            border-radius: 12px;
            box-shadow: 6px 6px 0 rgba(18, 24, 38, .12);
            animation: none;
            transform: rotate(4deg);
        }

        .phone.work-mode .topbar {
            gap: 9px;
            padding: max(12px, env(safe-area-inset-top)) 14px 10px;
            background: rgba(248, 251, 255, .98);
            box-shadow: 0 6px 0 rgba(18, 24, 38, .08);
        }

        .phone.work-mode .brand {
            width: 40px;
            height: 40px;
            background: #121826;
            border-radius: 8px;
            color: #b7ffe8;
            font-size: 19px;
            box-shadow: none;
            transform: rotate(0);
        }

        .phone.work-mode .brand-copy h1 {
            font-family: "Jua", ui-rounded, system-ui, sans-serif;
            font-size: 22px;
            line-height: 1;
        }

        .phone.work-mode .brand-copy p {
            color: #0b776a;
            font-size: 11px;
        }

        .phone.work-mode .mode-switch {
            gap: 2px;
            padding: 2px;
            background: #eef3fb;
            border-radius: 8px;
            box-shadow: none;
        }

        .phone.work-mode .mode-button {
            min-width: 42px;
            min-height: 28px;
            border-radius: 6px;
            font-size: 11px;
        }

        .phone.work-mode .mode-button.is-active {
            background: #121826;
            color: #b7ffe8;
        }

        .phone.work-mode .marquee {
            width: 100%;
            margin: 0 0 13px;
            background: #ffffff;
            color: #121826;
            border: var(--line);
            border-radius: 8px;
            box-shadow: 3px 3px 0 rgba(18, 24, 38, .16);
            font-size: 12px;
        }

        .phone.work-mode .marquee span {
            padding: 8px 12px;
            animation-duration: 22s;
        }

        .phone.work-mode .hero {
            min-height: 220px;
            margin-bottom: 16px;
            padding: 14px;
            background:
                linear-gradient(180deg, #ffffff 0 36px, #f5f8fd 36px),
                linear-gradient(90deg, rgba(18, 24, 38, .05) 1px, transparent 1px);
            background-size: auto, 18px 18px;
            border: var(--line);
            border-radius: 12px;
            box-shadow: 6px 6px 0 rgba(18, 24, 38, .18);
        }

        .phone.work-mode .hero::before {
            content: "";
            position: absolute;
            left: 13px;
            top: 14px;
            width: 54px;
            height: 8px;
            background: #d9ffe8;
            border: var(--line);
            border-radius: 999px;
        }

        .phone.work-mode .hero::after {
            content: "";
            position: absolute;
            left: 76px;
            top: 17px;
            width: 96px;
            height: 3px;
            background: #c5cfdf;
            box-shadow: 0 8px 0 #d9e1ef;
        }

        .phone.work-mode .hero-title {
            margin-top: 42px;
            max-width: 194px;
            color: #121826;
            font-family: "Jua", ui-rounded, system-ui, sans-serif;
            font-size: clamp(44px, 13vw, 57px);
            line-height: .98;
        }

        .phone.work-mode .hero-title span {
            background: #b7ffe8;
            border-radius: 7px;
            margin: 4px 0 6px;
            padding-bottom: 3px;
            box-shadow: 3px 3px 0 var(--ink);
            transform: rotate(0);
        }

        .phone.work-mode .mascot-scene,
        .phone.work-mode .mascot {
            display: none;
        }

        .phone.work-mode .office-mascot {
            display: block;
        }

        .phone.work-mode .stamp {
            right: 16px;
            bottom: 14px;
            width: 86px;
            height: 46px;
            background: #121826;
            border-radius: 7px;
            color: #b7ffe8;
            font-family: "Jua", ui-rounded, system-ui, sans-serif;
            font-size: 13px;
            line-height: 1.02;
            text-shadow: none;
            box-shadow: 3px 3px 0 rgba(18, 24, 38, .25);
            transform: rotate(0);
        }

        .phone.work-mode .panel,
        .phone.work-mode .panel:nth-of-type(2n),
        .phone.work-mode .panel:nth-of-type(3n) {
            margin-top: 13px;
            padding: 14px;
            background: #ffffff;
            border-radius: 10px;
            box-shadow: 4px 4px 0 rgba(18, 24, 38, .18);
            transform: none;
        }

        .phone.work-mode .step {
            top: -12px;
            background: #d9ffe8;
            border-radius: 5px;
            color: #121826;
            font-size: 11px;
            box-shadow: none;
            transform: none;
        }

        .phone.work-mode .panel-title {
            margin-top: 12px;
            color: #273348;
            font-size: 12px;
        }

        .phone.work-mode .panel-title::after {
            height: 1px;
            background: #a9b5c9;
        }

        .phone.work-mode .hint {
            color: #536071;
            font-size: 12px;
            font-weight: 800;
        }

        .phone.work-mode .message-panel {
            background: #f1f6ff;
        }

        .phone.work-mode .style-panel {
            background: #eef3fb;
        }

        .phone.work-mode .voice-prompt-card,
        .phone.work-mode .style-answer-pill {
            background: #f8fbff;
            border-radius: 7px;
            box-shadow: 3px 3px 0 rgba(18, 24, 38, .18);
        }

        .phone.work-mode .voice-prompt-card span {
            background: #121826;
            color: #b7ffe8;
        }

        .phone.work-mode .style-input {
            min-height: 72px;
            background: #fff;
            font-size: 15px;
        }

        .phone.work-mode .style-next,
        .phone.work-mode .style-sync,
        .phone.work-mode .style-clear {
            border-radius: 7px;
            box-shadow: 3px 3px 0 rgba(18, 24, 38, .22);
        }

        .phone.work-mode .style-next {
            background: #121826;
            color: #b7ffe8;
        }

        .phone.work-mode .style-sync {
            background: #d9ffe8;
        }

        .phone.work-mode .style-summary {
            background: #f8fbff;
            border-radius: 8px;
            box-shadow: 3px 3px 0 rgba(18, 24, 38, .18);
        }

        .phone.work-mode .style-tag {
            background: #eef3fb;
            border-radius: 7px;
        }

        .phone.work-mode .chip {
            border-radius: 7px;
            background: #f8fbff;
            box-shadow: 2px 2px 0 rgba(18, 24, 38, .22);
            font-size: 13px;
        }

        .phone.work-mode .chip.is-active {
            background: #121826;
            color: #b7ffe8;
            transform: translate(-1px, -1px);
        }

        .phone.work-mode input,
        .phone.work-mode textarea {
            background: #fff;
            border-radius: 7px;
            box-shadow: inset 0 0 0 2px rgba(18, 24, 38, .04);
        }

        .phone.work-mode textarea {
            min-height: 112px;
            font-size: 18px;
        }

        .phone.work-mode .draft-input {
            min-height: 78px;
            background: #ffffff;
        }

        .phone.work-mode .select-wrap {
            background: #f8fbff;
            border-radius: 7px;
            box-shadow: 3px 3px 0 rgba(18, 24, 38, .22);
        }

        .phone.work-mode .field:nth-child(3) .select-wrap {
            background: #f8fbff;
        }

        .phone.work-mode .select-menu {
            background: rgba(248, 251, 255, .98);
            border-radius: 10px;
            box-shadow: 5px 5px 0 rgba(18, 24, 38, .2);
        }

        .phone.work-mode .select-option {
            border-radius: 7px;
            box-shadow: 2px 2px 0 rgba(18, 24, 38, .2);
        }

        .phone.work-mode .select-option.is-selected {
            background: #121826;
            color: #b7ffe8;
        }

        .phone.work-mode .roll,
        .phone.work-mode .roll.is-loading {
            background: #121826;
            color: #b7ffe8;
            border-radius: 7px;
            box-shadow: 4px 4px 0 rgba(18, 24, 38, .24);
        }

        .phone.work-mode .dice {
            background: #d9ffe8;
            border-radius: 7px;
            box-shadow: 4px 4px 0 rgba(18, 24, 38, .24);
        }

        .phone.work-mode .brief {
            gap: 7px;
        }

        .phone.work-mode .brief div {
            min-height: 48px;
            background: #ffffff;
            border-radius: 7px;
            box-shadow: 2px 2px 0 rgba(18, 24, 38, .18);
        }

        .phone.work-mode .brief div:nth-child(2) {
            background: #d9ffe8;
        }

        .phone.work-mode .brief div:nth-child(3) {
            background: #e3e9ff;
            color: var(--ink);
        }

        .phone.work-mode .warning-card,
        .phone.work-mode .result-panel,
        .phone.work-mode .conference-panel,
        .phone.work-mode .compare-card {
            border-radius: 8px;
            box-shadow: 3px 3px 0 rgba(18, 24, 38, .18);
        }

        .phone.work-mode .conference-toggle,
        .phone.work-mode .chat-send,
        .phone.work-mode .context-regenerate,
        .phone.work-mode .conference-close {
            border-radius: 7px;
            box-shadow: 3px 3px 0 rgba(18, 24, 38, .2);
        }

        .phone.work-mode .conference-toggle,
        .phone.work-mode .chat-send {
            background: #121826;
            color: #b7ffe8;
        }

        .phone.work-mode .conference-panel {
            background: #ffffff;
        }

        .phone.work-mode .chat-bubble {
            box-shadow: 2px 2px 0 rgba(18, 24, 38, .18);
        }

        .phone.work-mode .chat-bubble.user {
            background: #121826;
            color: #b7ffe8;
        }

        .phone.work-mode .chat-bubble.assistant,
        .phone.work-mode .context-regenerate {
            background: #d9ffe8;
            color: #121826;
        }

        .phone.work-mode .context-chip {
            background: #eef3fb;
        }

        .phone.work-mode .warning-card.ok {
            background: #d9ffe8;
        }

        .phone.work-mode .warning-card.watch {
            background: #fff4c5;
        }

        .phone.work-mode .warning-card.danger {
            background: #ffe2e9;
        }

        .phone.work-mode .tone-chip,
        .phone.work-mode .view-button {
            border-radius: 7px;
            background: #f8fbff;
            box-shadow: 2px 2px 0 rgba(18, 24, 38, .2);
        }

        .phone.work-mode .view-button.is-active,
        .phone.work-mode .tone-chip:active {
            background: #121826;
            color: #b7ffe8;
            transform: translate(-1px, -1px);
        }

        .phone.work-mode .compare-card:nth-child(even) {
            background: #f1f6ff;
        }

        .phone.work-mode .reply,
        .phone.work-mode .reply:nth-child(even) {
            justify-self: stretch;
            width: 100%;
            background: #ffffff;
            border-radius: 8px;
            box-shadow: 4px 4px 0 rgba(18, 24, 38, .2);
            transform: none;
        }

        .phone.work-mode .reply:nth-child(even) {
            background: #f1f6ff;
        }

        .phone.work-mode .reply strong {
            background: #121826;
            color: #b7ffe8;
        }

        .phone.work-mode .reply-next {
            background: #f8fbff;
            border-color: #121826;
        }

        .is-popping {
            animation: pop .46s cubic-bezier(.2, 1.7, .4, 1);
        }

        @media (min-width: 520px) {
            body {
                min-height: 100vh;
                padding: 24px;
                align-items: center;
            }

            .phone {
                min-height: min(860px, calc(100vh - 48px));
                max-height: 860px;
                border: 3px solid var(--ink);
                border-radius: 32px;
                box-shadow: 16px 16px 0 rgba(23, 19, 15, .48);
                overflow-y: auto;
                scrollbar-color: transparent transparent;
            }

            .topbar {
                border-top-left-radius: 29px;
                border-top-right-radius: 29px;
            }
        }

        @keyframes ticker {
            to {
                transform: translateX(-100%);
            }
        }

        @keyframes dateMascotDance {
            0%, 100% {
                transform: translateY(0) rotate(8deg) scale(1);
            }
            12% {
                transform: translateY(-14px) rotate(4deg) scale(1.03, .98);
            }
            22% {
                transform: translateY(3px) rotate(11deg) scale(.98, 1.03);
            }
            34% {
                transform: translateY(-9px) rotate(2deg) scale(1.02);
            }
            48% {
                transform: translateY(0) rotate(9deg) scale(1);
            }
            62% {
                transform: translateY(-5px) rotate(13deg) scale(1.01);
            }
            74% {
                transform: translateY(2px) rotate(6deg) scale(.99, 1.02);
            }
        }

        @keyframes dateFaceAct {
            0%, 100% {
                transform: translateY(0) rotate(0) scale(1);
            }
            12%, 18% {
                transform: translateY(-2px) rotate(-2deg) scale(1.01);
            }
            34%, 44% {
                transform: translateY(1px) rotate(2deg) scale(.99, 1.02);
            }
            66%, 76% {
                transform: translateY(-1px) rotate(-1deg) scale(1.01);
            }
        }

        @keyframes starPulse {
            0%, 100% {
                transform: rotate(-10deg) scale(.91);
            }
            50% {
                transform: rotate(-6deg) scale(.97);
            }
        }

        @keyframes dateCapAct {
            0%, 100% {
                transform: rotate(-4deg) translateY(0);
            }
            12%, 18% {
                transform: rotate(-6deg) translateY(-2px);
            }
            66%, 76% {
                transform: rotate(-3deg) translateY(-1px);
            }
        }

        @keyframes dateBrimAct {
            0%, 100% {
                transform: rotate(-4deg) translateY(0);
            }
            12%, 18% {
                transform: rotate(-6deg) translateY(1px);
            }
            66%, 76% {
                transform: rotate(-3deg) translateY(0);
            }
        }

        @keyframes dateGlasses {
            0%, 9%, 22%, 100% {
                transform: rotate(2deg) translateY(0);
            }
            12%, 17% {
                transform: rotate(2deg) translateY(1px);
            }
        }

        @keyframes sparkleBlink {
            0%, 38%, 58%, 100% {
                opacity: .65;
                transform: rotate(-17deg) scale(.72);
            }
            45%, 51% {
                opacity: 1;
                transform: rotate(4deg) scale(1.08);
            }
        }

        @keyframes dateWink {
            0%, 64%, 82%, 100% {
                opacity: 0;
                transform: rotate(-17deg) scaleX(0);
            }
            70%, 75% {
                opacity: 1;
                transform: rotate(-17deg) scaleX(1);
            }
        }

        @keyframes dateEyeDot {
            0%, 10%, 20%, 100% {
                opacity: 1;
                transform: translateY(0) scale(1);
            }
            13%, 16% {
                opacity: 0;
                transform: translateY(0) scale(.85);
            }
        }

        @keyframes dateWinkLine {
            0%, 10%, 20%, 100% {
                opacity: 0;
                transform: rotate(-7deg) scaleX(.65);
            }
            13%, 16% {
                opacity: 1;
                transform: rotate(-7deg) scaleX(1);
            }
        }

        @keyframes dateKissFace {
            0%, 58%, 82%, 100% {
                transform: rotate(-14deg) scaleY(.15);
            }
            64%, 73% {
                transform: rotate(-14deg) scaleY(1);
            }
        }

        @keyframes dateKissPop {
            0%, 60%, 86%, 100% {
                opacity: 0;
                transform: translate(0, 0) rotate(-8deg) scale(.45);
            }
            66% {
                opacity: 1;
                transform: translate(12px, -8px) rotate(-6deg) scale(1);
            }
            78% {
                opacity: .9;
                transform: translate(35px, -24px) rotate(7deg) scale(1.16);
            }
        }

        @keyframes officeFocus {
            0%, 100% {
                transform: translateY(0) rotate(0);
            }
            14%, 36% {
                transform: translateY(-1px) rotate(-1deg);
            }
            28% {
                transform: translateY(-3px) rotate(1deg);
            }
        }

        @keyframes glassesAdjust {
            0%, 12%, 42%, 100% {
                transform: translateY(0) rotate(0);
            }
            20%, 32% {
                transform: translateY(-4px) rotate(-2deg);
            }
            38% {
                transform: translateY(1px) rotate(1deg);
            }
        }

        @keyframes handAdjust {
            0%, 12%, 44%, 100% {
                opacity: 0;
                transform: translate(8px, 12px) rotate(8deg) scale(.92);
            }
            19% {
                opacity: .95;
                transform: translate(3px, 4px) rotate(-3deg) scale(.98);
            }
            27%, 34% {
                opacity: 1;
                transform: translate(0, -1px) rotate(-12deg) scale(1);
            }
            39% {
                opacity: .72;
                transform: translate(3px, 5px) rotate(-2deg) scale(.96);
            }
        }

        @keyframes paperLift {
            0%, 48%, 100% {
                opacity: 0;
                transform: translateY(62px) rotate(7deg);
            }
            56% {
                opacity: 1;
                transform: translateY(18px) rotate(4deg);
            }
            66%, 80% {
                opacity: 1;
                transform: translateY(-6px) rotate(-3deg);
            }
            90% {
                opacity: 1;
                transform: translateY(17px) rotate(5deg);
            }
        }

        @keyframes floaty {
            0%, 100% {
                transform: translateY(0) rotate(8deg);
            }
            50% {
                transform: translateY(-12px) rotate(3deg);
            }
        }

        @keyframes blob {
            0%, 100% {
                transform: rotate(-9deg) scale(1);
            }
            50% {
                transform: rotate(8deg) scale(1.07);
            }
        }

        @keyframes nudge {
            0%, 100% {
                transform: rotate(2deg);
            }
            50% {
                transform: rotate(-3deg) translateY(-2px);
            }
        }

        @keyframes pop {
            0% {
                transform: scale(.96) rotate(-2deg);
            }
            55% {
                transform: scale(1.035) rotate(2deg);
            }
            100% {
                transform: scale(1) rotate(0);
            }
        }

        @media (prefers-reduced-motion: reduce) {
            .date-mascot::before,
            .date-cap,
            .date-brim,
            .date-face,
            .date-glasses,
            .date-eye,
            .date-wink-line,
            .date-glint,
            .date-tongue,
            .date-pop-kiss,
            .mascot,
            .office-worker,
            .office-glasses,
            .office-hand,
            .office-paper,
            .phone::before,
            .phone::after,
            .marquee span {
                animation: none;
            }
        }
    </style>
</head>
<body>
    <main class="phone" aria-label="RE:BOUND reply generator">
        <header class="topbar">
            <div class="brand">R</div>
            <div class="brand-copy">
                <h1>RE:BOUND</h1>
                <p id="brand-subtitle">썸톡 작전실</p>
            </div>
            <div class="mode-switch" role="group" aria-label="reply mode">
                <button class="mode-button is-active" type="button" data-mode="date" aria-pressed="true">썸톡</button>
                <button class="mode-button" type="button" data-mode="work" aria-pressed="false">직장</button>
            </div>
        </header>

        <section class="stage">
            <div class="marquee" aria-hidden="true">
                <span data-copy="marquee">작전 회의중 · MBTI는 참고만 · 너무 착한 답장 금지 · 말은 가볍게 심장은 몰래 · </span>
                <span data-copy="marquee">작전 회의중 · MBTI는 참고만 · 너무 착한 답장 금지 · 말은 가볍게 심장은 몰래 · </span>
            </div>

            <div class="hero">
                <h2 class="hero-title" id="hero-title">썸톡<br><span>작전</span><br>개시</h2>
                <div class="mascot-scene" aria-hidden="true">
                    <div class="date-mascot">
                        <span class="date-cap"></span>
                        <span class="date-brim"></span>
                        <span class="date-horn left"></span>
                        <span class="date-horn right"></span>
                        <span class="date-tail"></span>
                        <span class="date-face"></span>
                        <span class="date-glasses"><span class="date-eye left"></span><span class="date-eye right"></span><span class="date-wink-line"></span><span class="date-bridge"></span></span>
                        <span class="date-glint"></span>
                        <span class="date-mouth"></span>
                        <span class="date-tongue"></span>
                        <span class="date-pop-kiss"></span>
                    </div>
                </div>
                <div class="office-mascot" aria-hidden="true">
                    <div class="office-worker">
                        <div class="office-head">
                            <span class="office-hair"></span>
                            <span class="office-glasses"></span>
                            <span class="office-mouth"></span>
                        </div>
                        <div class="office-body">
                            <span class="office-shirt"></span>
                            <span class="office-tie"></span>
                            <span class="office-badge"></span>
                        </div>
                        <span class="office-hand"></span>
                    </div>
                    <div class="office-paper"></div>
                    <div class="office-laptop"></div>
                </div>
                <div class="stamp" id="hero-stamp">답장<br>작전<br>개시</div>
            </div>

            <section class="panel" id="relation-panel">
                <div class="step" id="relation-step">01 관계</div>
                <div class="panel-title" id="relation-title">지금 둘 사이</div>
                <p class="hint" id="relation-hint">정답 말고 느낌만 골라. 얘가 답장 온도를 정해줌.</p>
                <div class="chips wrap" data-group="relation">
                    <button class="chip is-active" data-value="crush">썸 타는 중</button>
                    <button class="chip" data-value="first">처음 연락</button>
                    <button class="chip" data-value="date1">한 번 만남</button>
                    <button class="chip" data-value="fading">애매하게 식는 중</button>
                    <button class="chip" data-value="friend">친구인데 묘함</button>
                    <button class="chip" data-value="ex">전 애인/재회각</button>
                </div>
            </section>

            <section class="panel" id="profile-panel">
                <div class="step blue" id="profile-step">02 상대</div>
                <div class="panel-title" id="profile-title">상대 디테일</div>
                <p class="hint" id="profile-hint">MBTI는 점쟁이 모드 말고 말투 조절용 힌트로만 씀.</p>
                <div class="profile-grid">
                    <div class="field">
                        <label for="mbti" id="mbti-label">MBTI</label>
                        <input id="mbti" maxlength="4" placeholder="ENFP">
                    </div>
                    <div class="field">
                        <label for="age" id="age-label">나이</label>
                        <div class="select-wrap custom-select" data-select="age" data-value="">
                            <button class="select-button" type="button" id="age" aria-haspopup="listbox" aria-expanded="false">
                                <span class="select-value">모름</span>
                            </button>
                            <div class="select-menu" role="listbox" aria-labelledby="age">
                                <button class="select-option is-selected" type="button" role="option" aria-selected="true" data-value="">모름</button>
                                <button class="select-option" type="button" role="option" aria-selected="false" data-value="20대 초반">20대 초반</button>
                                <button class="select-option" type="button" role="option" aria-selected="false" data-value="20대 후반">20대 후반</button>
                                <button class="select-option" type="button" role="option" aria-selected="false" data-value="30대 초반">30대 초반</button>
                                <button class="select-option" type="button" role="option" aria-selected="false" data-value="30대 후반">30대 후반</button>
                                <button class="select-option" type="button" role="option" aria-selected="false" data-value="40대 이상">40대 이상</button>
                            </div>
                        </div>
                    </div>
                    <div class="field">
                        <label for="gender" id="gender-label">성별</label>
                        <div class="select-wrap custom-select" data-select="gender" data-value="">
                            <button class="select-button" type="button" id="gender" aria-haspopup="listbox" aria-expanded="false">
                                <span class="select-value">상관없음</span>
                            </button>
                            <div class="select-menu" role="listbox" aria-labelledby="gender">
                                <button class="select-option is-selected" type="button" role="option" aria-selected="true" data-value="">상관없음</button>
                                <button class="select-option" type="button" role="option" aria-selected="false" data-value="남성">남성</button>
                                <button class="select-option" type="button" role="option" aria-selected="false" data-value="여성">여성</button>
                                <button class="select-option" type="button" role="option" aria-selected="false" data-value="논바이너리">논바이너리</button>
                            </div>
                        </div>
                    </div>
                    <div class="field">
                        <label for="job" id="job-label">직업</label>
                        <input id="job" placeholder="디자이너">
                    </div>
                </div>

                <div class="panel-title" id="contact-title">연락 스타일</div>
                <div class="chips" data-group="contact">
                    <button class="chip is-active" data-value="normal">보통</button>
                    <button class="chip" data-value="fast">답장 빠름</button>
                    <button class="chip" data-value="slow">느림</button>
                    <button class="chip" data-value="dry">질문 적음</button>
                    <button class="chip" data-value="long">장문형</button>
                    <button class="chip" data-value="seen">읽씹 있음</button>
                </div>
            </section>

            <section class="panel style-panel" id="style-panel">
                <div class="step mint" id="style-step">03 말투</div>
                <div class="panel-title" id="style-title">말투 싱크</div>
                <p class="hint" id="style-hint">상대 예시를 보고 내가 보낼 답장만 써줘. 다음 누르면 새 예시로 넘어감.</p>
                <div class="voice-prompt-card">
                    <span id="style-prompt-count">01/05</span>
                    <strong id="style-prompt-label">상대 예시</strong>
                    <p id="style-prompt-text">오늘 뭐해?</p>
                </div>
                <textarea id="style-answer" class="style-input" maxlength="180" placeholder="나 지금 집이랑 한 몸 됨ㅋㅋ 너는?"></textarea>
                <textarea id="style-samples" class="style-storage" aria-hidden="true" tabindex="-1"></textarea>
                <div class="style-actions">
                    <button class="style-next" type="button" id="style-next">다음</button>
                    <button class="style-sync" type="button" id="style-sync">말투 분석</button>
                    <button class="style-clear" type="button" id="style-clear">초기화</button>
                </div>
                <div class="style-answer-list" id="style-answer-list"></div>
                <div class="style-summary is-empty" id="style-summary">
                    <strong id="style-summary-title">말투 프로필</strong>
                    <p id="style-summary-text"></p>
                    <div class="style-tags" id="style-tags"></div>
                </div>
            </section>

            <section class="panel message-panel" id="composer">
                <div class="step pink" id="message-step">04 톡</div>
                <div class="panel-title" id="message-title">상대가 보낸 말</div>
                <textarea id="message" maxlength="220" placeholder="상대 톡을 그대로 붙여넣어줘">오늘 뭐해?</textarea>

                <div class="panel-title" id="draft-title">내가 쓰려던 답장</div>
                <textarea id="draft" class="draft-input" maxlength="180" placeholder="있으면 넣어줘. 보내기 전에 독 묻었는지 봐줄게."></textarea>

                <div class="panel-title" id="goal-title">내 목표</div>
                <div class="chips" data-group="goal">
                    <button class="chip is-active" data-value="keep">대화 살리기</button>
                    <button class="chip" data-value="date">약속 잡기</button>
                    <button class="chip" data-value="like">호감 티내기</button>
                    <button class="chip" data-value="tease">살짝 떠보기</button>
                    <button class="chip" data-value="line">선 긋기</button>
                    <button class="chip" data-value="cool">안 매달려 보이기</button>
                </div>

                <div class="actions">
                    <button class="roll" id="roll">답장 추천받기</button>
                    <button class="dice" id="dice" aria-label="randomize">↯</button>
                </div>
            </section>

            <section class="brief" aria-label="reply diagnosis">
                <div id="briefRelation">썸 온도 중간</div>
                <div id="briefProfile">정보 적당함</div>
                <div id="briefRisk">리스크 낮음</div>
            </section>

            <section class="result-tools is-empty" id="result-tools" aria-live="polite">
                <div class="warning-card ok" id="warning-card">
                    <strong id="warning-title">초안 점검</strong>
                    <p id="warning-text">답장을 받으면 여기에 보내기 전 경고가 뜸.</p>
                </div>
                <div class="result-panel">
                    <div class="panel-title" id="tone-title">톤 다시 굴리기</div>
                    <div class="tone-options" id="tone-options"></div>
                    <div class="view-toggle" role="group" aria-label="recommendation view">
                        <button class="view-button is-active" type="button" data-view="cards">카드</button>
                        <button class="view-button" type="button" data-view="compare">비교</button>
                    </div>
                    <button class="conference-toggle" id="conference-toggle" type="button">작전 회의 열기</button>
                </div>
            </section>

            <section class="conference-panel is-empty" id="conference-panel" aria-live="polite">
                <div class="conference-head">
                    <div class="panel-title" id="conference-title">작전 회의</div>
                    <button class="conference-close" id="conference-close" type="button" aria-label="close">×</button>
                </div>
                <p class="conference-hint" id="conference-hint">앞뒤 상황을 말해주면 답장 작전을 다시 잡아줌.</p>
                <div class="context-chip" id="context-chip"></div>
                <div class="chat-log" id="chat-log"></div>
                <div class="chat-compose">
                    <textarea class="chat-input" id="chat-input" maxlength="260" placeholder="어제 뭐가 있었는지 짧게 털어줘"></textarea>
                    <button class="chat-send" id="chat-send" type="button">↵</button>
                </div>
                <button class="context-regenerate" id="context-regenerate" type="button">이 맥락으로 다시 짜줘</button>
            </section>

            <section class="compare-view is-empty" id="compare-view" aria-live="polite"></section>
            <section class="replies is-empty" id="replies" aria-live="polite"></section>
        </section>

        <div class="toast" id="toast">복사됨. 이제 자연스러운 척만 하면 됨.</div>
    </main>

    <script>
        const phone = document.querySelector(".phone");
        const fields = {
            relation: document.querySelector('[data-group="relation"]'),
            contact: document.querySelector('[data-group="contact"]'),
            goal: document.querySelector('[data-group="goal"]'),
            mbti: document.querySelector("#mbti"),
            age: document.querySelector('[data-select="age"]'),
            gender: document.querySelector('[data-select="gender"]'),
            job: document.querySelector("#job"),
            message: document.querySelector("#message"),
            draft: document.querySelector("#draft"),
            styleSamples: document.querySelector("#style-samples"),
            styleAnswer: document.querySelector("#style-answer")
        };

        const copy = {
            brandSubtitle: document.querySelector("#brand-subtitle"),
            marquee: [...document.querySelectorAll('[data-copy="marquee"]')],
            heroTitle: document.querySelector("#hero-title"),
            heroStamp: document.querySelector("#hero-stamp"),
            relationStep: document.querySelector("#relation-step"),
            relationTitle: document.querySelector("#relation-title"),
            relationHint: document.querySelector("#relation-hint"),
            profileStep: document.querySelector("#profile-step"),
            profileTitle: document.querySelector("#profile-title"),
            profileHint: document.querySelector("#profile-hint"),
            styleStep: document.querySelector("#style-step"),
            styleTitle: document.querySelector("#style-title"),
            styleHint: document.querySelector("#style-hint"),
            mbtiLabel: document.querySelector("#mbti-label"),
            ageLabel: document.querySelector("#age-label"),
            genderLabel: document.querySelector("#gender-label"),
            jobLabel: document.querySelector("#job-label"),
            contactTitle: document.querySelector("#contact-title"),
            messageStep: document.querySelector("#message-step"),
            messageTitle: document.querySelector("#message-title"),
            draftTitle: document.querySelector("#draft-title"),
            goalTitle: document.querySelector("#goal-title"),
            toneTitle: document.querySelector("#tone-title"),
            modeButtons: [...document.querySelectorAll(".mode-button")]
        };

        const replies = document.querySelector("#replies");
        const resultTools = document.querySelector("#result-tools");
        const warningCard = document.querySelector("#warning-card");
        const warningTitle = document.querySelector("#warning-title");
        const warningText = document.querySelector("#warning-text");
        const toneOptions = document.querySelector("#tone-options");
        const viewButtons = [...document.querySelectorAll(".view-button")];
        const compareView = document.querySelector("#compare-view");
        const conferenceToggle = document.querySelector("#conference-toggle");
        const conferencePanel = document.querySelector("#conference-panel");
        const conferenceClose = document.querySelector("#conference-close");
        const conferenceTitle = document.querySelector("#conference-title");
        const conferenceHint = document.querySelector("#conference-hint");
        const contextChip = document.querySelector("#context-chip");
        const chatLog = document.querySelector("#chat-log");
        const chatInput = document.querySelector("#chat-input");
        const chatSend = document.querySelector("#chat-send");
        const contextRegenerate = document.querySelector("#context-regenerate");
        const styleSync = document.querySelector("#style-sync");
        const styleNext = document.querySelector("#style-next");
        const styleClear = document.querySelector("#style-clear");
        const styleSummary = document.querySelector("#style-summary");
        const styleSummaryText = document.querySelector("#style-summary-text");
        const styleTags = document.querySelector("#style-tags");
        const stylePromptCount = document.querySelector("#style-prompt-count");
        const stylePromptText = document.querySelector("#style-prompt-text");
        const stylePromptLabel = document.querySelector("#style-prompt-label");
        const styleAnswerList = document.querySelector("#style-answer-list");
        const roll = document.querySelector("#roll");
        const dice = document.querySelector("#dice");
        const composer = document.querySelector("#composer");
        const toast = document.querySelector("#toast");
        const briefRelation = document.querySelector("#briefRelation");
        const briefProfile = document.querySelector("#briefProfile");
        const briefRisk = document.querySelector("#briefRisk");
        let hasRecommendation = false;
        let currentMode = "date";
        let activeResultView = "cards";
        let lastResult = null;
        let styleProfile = "";
        let styleProfileTags = [];
        let styleAnswers = [];
        let stylePromptIndex = 0;
        let chatMessages = [];
        let contextSummary = "";
        let chatBusy = false;
        let chatInputComposing = false;
        let lastChatSubmitText = "";
        let lastChatSubmitAt = 0;
        let hasAppliedMode = false;

        const modes = {
            date: {
                brandSubtitle: "썸톡 작전실",
                marquee: "작전 회의중 · MBTI는 참고만 · 너무 착한 답장 금지 · 말은 가볍게 심장은 몰래 · ",
                heroTitle: "썸톡<br><span>작전</span><br>개시",
                heroStamp: "답장<br>작전<br>개시",
                steps: ["01 관계", "02 상대", "03 말투", "04 톡"],
                titles: {
                    relation: "지금 둘 사이",
                    profile: "상대 디테일",
                    style: "말투 싱크",
                    contact: "연락 스타일",
                    message: "상대가 보낸 말",
                    draft: "내가 쓰려던 답장",
                    goal: "내 목표"
                },
                hints: {
                    relation: "정답 말고 느낌만 골라. 얘가 답장 온도를 정해줌.",
                    profile: "MBTI는 점쟁이 모드 말고 말투 조절용 힌트로만 씀.",
                    style: "상대 예시를 보고 내가 보낼 답장만 써줘. 다음 누르면 새 예시로 넘어감."
                },
                fieldLabels: { mbti: "MBTI", age: "나이", gender: "성별", job: "직업" },
                placeholders: {
                    mbti: "ENFP",
                    job: "디자이너",
                    message: "상대 톡을 그대로 붙여넣어줘",
                    draft: "있으면 넣어줘. 보내기 전에 독 묻었는지 봐줄게.",
                    styleAnswer: "나 지금 집이랑 한 몸 됨ㅋㅋ 너는?",
                    defaultMessage: "오늘 뭐해?"
                },
                stylePrompts: [
                    "오늘 뭐해?",
                    "다음에 밥 먹자",
                    "답장 늦어서 미안 ㅠ",
                    "주말에 뭐해?",
                    "아 ㅋㅋ 귀엽네"
                ],
                mbtiMax: 4,
                selects: {
                    age: [
                        ["", "모름"],
                        ["20대 초반", "20대 초반"],
                        ["20대 후반", "20대 후반"],
                        ["30대 초반", "30대 초반"],
                        ["30대 후반", "30대 후반"],
                        ["40대 이상", "40대 이상"]
                    ],
                    gender: [
                        ["", "상관없음"],
                        ["남성", "남성"],
                        ["여성", "여성"],
                        ["논바이너리", "논바이너리"]
                    ]
                },
                options: {
                    relation: [
                        ["crush", "썸 타는 중"],
                        ["first", "처음 연락"],
                        ["date1", "한 번 만남"],
                        ["fading", "애매하게 식는 중"],
                        ["friend", "친구인데 묘함"],
                        ["ex", "전 애인/재회각"]
                    ],
                    contact: [
                        ["normal", "보통"],
                        ["fast", "답장 빠름"],
                        ["slow", "느림"],
                        ["dry", "질문 적음"],
                        ["long", "장문형"],
                        ["seen", "읽씹 있음"]
                    ],
                    goal: [
                        ["keep", "대화 살리기"],
                        ["date", "약속 잡기"],
                        ["like", "호감 티내기"],
                        ["tease", "살짝 떠보기"],
                        ["line", "선 긋기"],
                        ["cool", "안 매달려 보이기"]
                    ]
                },
                styles: ["safe", "bounce", "flirt", "spicy"],
                cardMeta: [
                    ["안전빵", "상대가 부담 안 느끼는 기본값"],
                    ["통통", "서비스 캐릭터가 제일 많이 묻은 답"],
                    ["살짝 플러팅", "호감은 보이는데 무릎은 안 꿇음"],
                    ["매운맛", "맛있지만 상황 봐야 하는 카드"]
                ],
                templates: {
                    keep: {
                        safe: "오늘은 그냥 이것저것 정리하는 중. 너는 뭐하고 있어?",
                        bounce: "오늘 뭐하냐는 질문이면 내 하루에 살짝 입장하려는 거지? 일단 통과.",
                        flirt: "딱히 큰 일정은 없는데, 너랑 얘기할 시간은 있음.",
                        spicy: "이 질문, 관심 없으면 안 하는 쪽으로 접수할게. 맞지?"
                    },
                    date: {
                        safe: "이번 주에 시간 맞으면 커피 한 잔 할래?",
                        bounce: "톡으로만 간 보기엔 데이터가 부족해. 실물 검증 한 번 하자.",
                        flirt: "나 너 보고 싶어졌는데. 이번 주 하루만 빌려줘.",
                        spicy: "우리 둘 다 바쁜 척 그만하고 날짜부터 고르자."
                    },
                    like: {
                        safe: "그 말 좀 좋게 들린다. 나만 그렇게 들은 거 아니지?",
                        bounce: "방금 톡 귀여움 점수 올라감. 억울하면 다음 답장으로 반박해.",
                        flirt: "나 지금 너한테 살짝 설레도 되는 타이밍으로 읽고 있어.",
                        spicy: "나 기대하게 만드는 중이면 꽤 성공적이야."
                    },
                    tease: {
                        safe: "그 말은 내가 좋게 해석해도 되는 쪽?",
                        bounce: "오. 이건 그냥 말인지 살짝 던진 건지 판독 필요.",
                        flirt: "나 혼자 의미 부여하면 억울하니까 힌트 하나만 더 줘.",
                        spicy: "지금 나 떠보는 거면, 나도 모른 척 못 해."
                    },
                    line: {
                        safe: "그 얘기는 아직 조금 빠른 것 같아. 우리 천천히 가자.",
                        bounce: "그 챕터는 아직 잠금 상태야. 다른 얘기는 환영.",
                        flirt: "분위기는 좋은데 속도는 천천히 가고 싶어.",
                        spicy: "그건 나는 아직 부담스러워. 선은 여기쯤 그을게."
                    },
                    cool: {
                        safe: "나 지금 정신없어서 짧게 답할게. 그래도 톡은 봤어.",
                        bounce: "나 바쁜 척 아니고 진짜 바쁨. 근데 답장은 하는 중.",
                        flirt: "답장 늦어도 관심 없는 건 아님. 이 정도 힌트면 됐지?",
                        spicy: "나 너무 쉽게 잡히는 타입은 아니라서. 그래도 네 톡은 봄."
                    }
                },
                toneTitle: "톤 다시 굴리기",
                conference: {
                    open: "작전 회의 열기",
                    title: "썸톡 작전 회의",
                    hint: "마지막 분위기랑 네 속마음을 말해주면 답장 작전을 다시 잡아줌.",
                    placeholder: "예: 어제는 분위기 좋았는데 오늘 답장이 갑자기 짧아졌어",
                    regenerate: "이 맥락으로 다시 짜줘",
                    first: "좋아, 작전 회의 열자. 마지막으로 분위기 좋았던 순간이 언제였어?"
                },
                toneOptions: [
                    ["mytone", "내 말투로"],
                    ["no_ai", "AI 티 제거"],
                    ["soft", "순한맛"],
                    ["witty", "더 통통"],
                    ["flirt", "플러팅 더"],
                    ["spicy", "매운맛 더"],
                    ["calm", "부담 덜"],
                    ["less_cringe", "덜 오글"],
                    ["more_me", "더 나답게"]
                ],
                loading: "작전 짜는 중...",
                rollText: "답장 추천받기",
                copyToast: "복사됨. 이제 자연스러운 척만 하면 됨."
            },
            work: {
                brandSubtitle: "회신 데스크",
                marquee: "업무 데스크 · 기한 먼저 · 책임 범위 선명하게 · 사과는 필요한 만큼만 · 다음 액션까지 정리 · ",
                heroTitle: "업무<br><span>회신</span><br>결재",
                heroStamp: "회신<br>검토<br>완료",
                steps: ["01 관계", "02 정보", "03 말투", "04 업무"],
                titles: {
                    relation: "업무 라인",
                    profile: "회신 정보",
                    style: "말투 싱크",
                    contact: "회신 톤",
                    message: "받은 업무 메시지",
                    draft: "내가 쓰려던 회신",
                    goal: "회신 목표"
                },
                hints: {
                    relation: "상대와의 거리감이 문장 높이를 정해줌. 굽신거림은 필요한 만큼만.",
                    profile: "직급/성향을 몰라도 괜찮음. 알면 더 업무답게 다듬음.",
                    style: "업무 예시를 보고 내가 보낼 회신만 써줘. 다음 누르면 새 예시로 넘어감."
                },
                fieldLabels: { mbti: "성향", age: "직급", gender: "범위", job: "직무" },
                placeholders: {
                    mbti: "급함/꼼꼼함",
                    job: "마케팅/개발",
                    message: "상대가 보낸 업무 톡/메일을 붙여넣어줘",
                    draft: "보내려던 문장이 있으면 넣어줘. 책임 폭탄인지 먼저 봄.",
                    styleAnswer: "확인해서 오늘 오후 중으로 공유드리겠습니다.",
                    defaultMessage: "내일까지 가능할까요?"
                },
                stylePrompts: [
                    "자료 언제 가능할까요?",
                    "이 건 내일까지 가능할까요?",
                    "회의 시간 변경 가능할까요?",
                    "추가 요청드립니다.",
                    "확인 부탁드립니다."
                ],
                mbtiMax: 16,
                selects: {
                    age: [
                        ["", "모름"],
                        ["실무자", "실무자"],
                        ["매니저", "매니저"],
                        ["팀장", "팀장"],
                        ["임원", "임원"],
                        ["고객", "고객"]
                    ],
                    gender: [
                        ["", "상관없음"],
                        ["내부", "내부"],
                        ["외부", "외부"],
                        ["고객", "고객"],
                        ["상사", "상사"],
                        ["동료", "동료"]
                    ]
                },
                options: {
                    relation: [
                        ["manager", "상사"],
                        ["peer", "동료"],
                        ["junior", "후배"],
                        ["client", "고객/거래처"],
                        ["partner", "협업사"],
                        ["recruiter", "인사/채용"]
                    ],
                    contact: [
                        ["biz_normal", "보통"],
                        ["urgent", "급한 건"],
                        ["soft", "부드럽게"],
                        ["short", "짧게"],
                        ["detail", "자세히"],
                        ["followup", "재촉 필요"]
                    ],
                    goal: [
                        ["confirm", "확인/수락"],
                        ["schedule", "일정 잡기"],
                        ["decline", "정중히 거절"],
                        ["nudge", "재촉하기"],
                        ["boundary", "범위 정리"],
                        ["summarize", "짧게 정리"]
                    ]
                },
                styles: ["polite", "short", "firm", "sense"],
                cardMeta: [
                    ["정중", "기분 상하지 않게 기본값"],
                    ["간결", "회의 사이에 보내도 안 긴 답"],
                    ["단호", "범위와 조건을 선명하게"],
                    ["센스", "딱딱함은 줄이고 일은 되게"]
                ],
                templates: {
                    confirm: {
                        polite: "네, 확인했습니다. 말씀주신 내용 기준으로 진행하겠습니다.",
                        short: "확인했습니다. 바로 진행하겠습니다.",
                        firm: "확인했습니다. 범위가 달라지면 진행 전에 먼저 공유드리겠습니다.",
                        sense: "네, 이 건은 제가 잡고 가겠습니다. 변동 생기면 바로 말씀드릴게요."
                    },
                    schedule: {
                        polite: "가능합니다. 저는 내일 오후 2시 이후가 괜찮은데, 편하신 시간 있으실까요?",
                        short: "내일 오후 2시 이후 가능합니다. 괜찮으신 시간 알려주세요.",
                        firm: "일정은 내일 오후 중으로 맞추면 좋겠습니다. 오전은 다른 건으로 어렵습니다.",
                        sense: "캘린더가 아직 살아있을 때 잡아두면 좋겠습니다. 내일 오후 어떠세요?"
                    },
                    decline: {
                        polite: "제안 감사합니다. 다만 이번 건은 현재 일정상 맡기 어려울 것 같습니다.",
                        short: "이번 건은 일정상 어렵습니다. 양해 부탁드립니다.",
                        firm: "현재 범위에서는 추가 진행이 어렵습니다. 필요하시면 가능한 대안을 정리해드리겠습니다.",
                        sense: "무리해서 받았다가 둘 다 피곤해지는 그림이라, 이번 건은 어렵겠습니다."
                    },
                    nudge: {
                        polite: "확인차 다시 말씀드립니다. 오늘 중 회신 가능하실까요?",
                        short: "오늘 중 확인 가능하실까요?",
                        firm: "이 건은 회신이 있어야 다음 단계 진행이 가능합니다. 오늘 중 확인 부탁드립니다.",
                        sense: "이 건이 지금 대기열 맨 앞에 서 있습니다. 오늘 중 확인 가능하실까요?"
                    },
                    boundary: {
                        polite: "이 부분은 제가 확인 가능한 범위가 아니라 담당자 확인 후 말씀드리겠습니다.",
                        short: "해당 내용은 제 담당 범위 밖이라 확인 후 공유드리겠습니다.",
                        firm: "이 건은 제 권한으로 확정하기 어렵습니다. 담당자 확인 없이 진행하기는 어렵겠습니다.",
                        sense: "여기서 제가 단독 결재권자인 척하면 사고라, 확인 후 말씀드리겠습니다."
                    },
                    summarize: {
                        polite: "정리하면, 우선 해당 내용 확인 후 가능한 일정과 범위를 다시 공유드리겠습니다.",
                        short: "정리해서 확인 후 다시 공유드리겠습니다.",
                        firm: "현재 기준으로는 일정과 범위 확인이 먼저 필요합니다. 확인 후 다음 단계 말씀드리겠습니다.",
                        sense: "한 줄로 정리하면, 확인 먼저 하고 무리수는 안 두는 방향으로 가겠습니다."
                    }
                },
                toneTitle: "업무 말투 재정리",
                conference: {
                    open: "회신 상황 정리",
                    title: "업무 회신 상황실",
                    hint: "기한, 책임 범위, 거절/조율 포인트를 말해주면 회신을 다시 정리함.",
                    placeholder: "예: 상대가 급하다고 하는데 우리 쪽 일정이 아직 확정 안 됐어",
                    regenerate: "이 맥락으로 다시 정리",
                    first: "상황실 열었습니다. 이 건에서 제일 중요한 건 기한, 책임 범위, 거절 중 뭐예요?"
                },
                toneOptions: [
                    ["mytone", "내 말투로"],
                    ["no_ai", "AI 티 제거"],
                    ["polite", "더 정중하게"],
                    ["short", "더 짧게"],
                    ["safe", "책임 덜 지게"],
                    ["deadline", "기한 넣기"]
                ],
                loading: "회신 정리 중...",
                rollText: "업무 답장 받기",
                copyToast: "복사됨. 이제 침착한 사람처럼 보내면 됨."
            }
        };

        const labels = Object.fromEntries(
            Object.values(modes).flatMap((mode) => (
                Object.values(mode.options).flatMap((items) => items)
            ))
        );

        const modeState = {
            date: null,
            work: null
        };

        function activeValue(groupName) {
            return document.querySelector(`[data-group="${groupName}"] .is-active`).dataset.value;
        }

        function currentConfig() {
            return modes[currentMode];
        }

        function cleanInput() {
            return fields.message.value.trim().replaceAll("\\n", " ");
        }

        function cleanDraft() {
            return fields.draft.value.trim().replaceAll("\\n", " ");
        }

        function cleanStyleSamples() {
            return fields.styleSamples.value.trim();
        }

        function cloneMessages(messages) {
            return messages.map((message) => ({ role: message.role, text: message.text }));
        }

        function defaultModeState(mode) {
            const config = modes[mode];
            return {
                relation: config.options.relation[0][0],
                contact: config.options.contact[0][0],
                goal: config.options.goal[0][0],
                mbti: "",
                age: config.selects.age[0][0],
                gender: config.selects.gender[0][0],
                job: "",
                message: config.placeholders.defaultMessage,
                draft: "",
                styleCurrentAnswer: "",
                styleAnswers: [],
                stylePromptIndex: 0,
                styleSamples: "",
                styleProfile: "",
                styleProfileTags: [],
                chatMessages: [],
                contextSummary: ""
            };
        }

        function saveModeState(mode = currentMode) {
            if (!modes[mode]) return;
            modeState[mode] = {
                relation: activeValue("relation"),
                contact: activeValue("contact"),
                goal: activeValue("goal"),
                mbti: fields.mbti.value,
                age: fields.age.dataset.value,
                gender: fields.gender.dataset.value,
                job: fields.job.value,
                message: fields.message.value,
                draft: fields.draft.value,
                styleCurrentAnswer: fields.styleAnswer.value,
                styleAnswers: [...styleAnswers],
                stylePromptIndex,
                styleSamples: fields.styleSamples.value,
                styleProfile,
                styleProfileTags: [...styleProfileTags],
                chatMessages: cloneMessages(chatMessages),
                contextSummary
            };
        }

        function stateForMode(mode) {
            return modeState[mode] || defaultModeState(mode);
        }

        function applyActiveChip(groupName, value) {
            const group = fields[groupName];
            const chips = [...group.querySelectorAll(".chip")];
            const active = chips.find((chip) => chip.dataset.value === value) || chips[0];
            chips.forEach((chip) => chip.classList.toggle("is-active", chip === active));
        }

        function applyCustomSelectValue(name, value) {
            const select = fields[name];
            const options = [...select.querySelectorAll(".select-option")];
            const selectedOption = options.find((option) => option.dataset.value === value) || options[0];
            select.dataset.value = selectedOption.dataset.value;
            select.querySelector(".select-value").textContent = selectedOption.textContent;
            options.forEach((option) => {
                const selected = option === selectedOption;
                option.classList.toggle("is-selected", selected);
                option.setAttribute("aria-selected", selected ? "true" : "false");
            });
        }

        function renderStoredStyleProfile() {
            styleTags.innerHTML = "";
            if (!styleProfile) {
                styleSummaryText.textContent = "";
                styleSummary.classList.add("is-empty");
                return;
            }
            styleSummaryText.textContent = `${styleProfile} 패턴 잡음.`;
            styleProfileTags.forEach((tag) => {
                const chip = document.createElement("span");
                chip.className = "style-tag";
                chip.textContent = tag;
                styleTags.appendChild(chip);
            });
            styleSummary.classList.remove("is-empty");
        }

        function currentStylePrompts() {
            return currentConfig().stylePrompts || [];
        }

        function buildStyleSamples() {
            const prompts = currentStylePrompts();
            return styleAnswers
                .map((answer, index) => {
                    const text = (answer || "").trim();
                    if (!text) return "";
                    return `상대: ${prompts[index % prompts.length] || "예시"}\\n나: ${text}`;
                })
                .filter(Boolean)
                .join("\\n\\n");
        }

        function rebuildStyleSamples() {
            fields.styleSamples.value = buildStyleSamples();
        }

        function renderStyleAnswers() {
            styleAnswerList.innerHTML = "";
            styleAnswers.forEach((answer, index) => {
                if (!answer) return;
                const pill = document.createElement("span");
                pill.className = "style-answer-pill";
                pill.textContent = `${String(index + 1).padStart(2, "0")} ${answer}`;
                styleAnswerList.appendChild(pill);
            });
        }

        function renderStylePrompt() {
            const prompts = currentStylePrompts();
            const total = Math.max(prompts.length, 1);
            stylePromptIndex = ((stylePromptIndex % total) + total) % total;
            stylePromptCount.textContent = `${String(stylePromptIndex + 1).padStart(2, "0")}/${String(total).padStart(2, "0")}`;
            stylePromptLabel.textContent = currentMode === "work" ? "업무 예시" : "상대 예시";
            stylePromptText.textContent = prompts[stylePromptIndex] || "오늘 뭐해?";
            fields.styleAnswer.placeholder = currentConfig().placeholders.styleAnswer;
            renderStyleAnswers();
        }

        function saveCurrentStyleAnswer({ silent = false } = {}) {
            const answer = fields.styleAnswer.value.trim();
            if (!answer) {
                if (!silent) {
                    showToast(currentMode === "work" ? "내 회신을 한 줄만 써줘." : "내 답장을 한 줄만 써줘.");
                    fields.styleAnswer.focus();
                }
                return false;
            }
            styleAnswers[stylePromptIndex] = answer;
            rebuildStyleSamples();
            renderStyleAnswers();
            clearRecommendation();
            return true;
        }

        function nextStylePrompt() {
            if (!saveCurrentStyleAnswer()) return;
            const prompts = currentStylePrompts();
            const count = Math.max(prompts.length, 1);
            if (cleanStyleSamples()) {
                renderStyleProfile(analyzeVoice(cleanStyleSamples()));
            }
            stylePromptIndex = (stylePromptIndex + 1) % count;
            fields.styleAnswer.value = styleAnswers[stylePromptIndex] || "";
            fields.styleAnswer.style.height = "auto";
            renderStylePrompt();
            showToast(`${styleAnswers.filter(Boolean).length}개 저장. 다음 말투 가자.`);
        }

        function profile() {
            const trait = fields.mbti.value.trim();
            return {
                mode: currentMode,
                relation: activeValue("relation"),
                contact: activeValue("contact"),
                goal: activeValue("goal"),
                mbti: currentMode === "date" ? trait.toUpperCase() : trait,
                age: fields.age.dataset.value,
                gender: fields.gender.dataset.value,
                job: fields.job.value.trim(),
                draft: cleanDraft(),
                styleSamples: cleanStyleSamples(),
                styleProfile,
                contextSummary,
                chatMessages
            };
        }

        function profileHint(data) {
            const bits = [];
            if (data.mode === "work") {
                if (data.mbti) bits.push(data.mbti);
                if (data.age) bits.push(data.age);
                if (data.gender) bits.push(data.gender);
                if (data.job) bits.push(`${data.job} 관련`);
                if (data.styleProfile) bits.push("말투 싱크 ON");
                if (data.contextSummary) bits.push("맥락 회의 ON");
                return bits.length ? bits.join(" · ") : "업무 정보 적게 입력됨";
            }
            if (data.mbti) {
                const energy = data.mbti[0] === "I" ? "초반엔 압박보다 여백" : data.mbti[0] === "E" ? "리액션은 조금 더 크게" : "MBTI는 가볍게 참고";
                bits.push(`${data.mbti}: ${energy}`);
            }
            if (data.age) bits.push(data.age);
            if (data.job) bits.push(`${data.job} 모드`);
            if (data.gender) bits.push(data.gender);
            if (data.styleProfile) bits.push("말투 싱크 ON");
            if (data.contextSummary) bits.push("맥락 회의 ON");
            return bits.length ? bits.join(" · ") : "상대 정보 적게 입력됨";
        }

        function extractMyLines(samples) {
            const lines = samples.split("\\n").map((line) => line.trim()).filter(Boolean);
            const mine = lines
                .filter((line) => /^(나|내|me|Me|ME)\\s*[:：]/.test(line))
                .map((line) => line.replace(/^(나|내|me|Me|ME)\\s*[:：]\\s*/, ""));
            if (mine.length) return mine;
            return lines
                .filter((line) => !/^(상대|걔|그 사람|상대방|you|You)\\s*[:：]/.test(line))
                .map((line) => line.replace(/^[-•]\\s*/, ""));
        }

        function analyzeVoice(samples) {
            const myLines = extractMyLines(samples);
            const joined = myLines.join(" ");
            const avgLength = myLines.length ? Math.round(myLines.reduce((sum, line) => sum + line.length, 0) / myLines.length) : 0;
            const tags = [];

            if (avgLength && avgLength <= 18) tags.push("짧게 침");
            if (avgLength > 38) tags.push("설명형");
            if (/ㅋ{1,}|ㅎㅎ|ㅎ{2,}/.test(joined)) tags.push("웃음 자주");
            if (/[~!♡♥]/.test(joined)) tags.push("리액션 있음");
            if (/(요|습니다|드립니다|세요)([.!?…~]*)($|\\s)/.test(joined)) tags.push("존댓말 기반");
            if (/(함|임|됨|중|듯|각|거지|아님|맞지)([.!?…~]*)($|\\s)/.test(joined)) tags.push("툭 치는 말끝");
            if (/(근데|일단|아니|증거|검증|반칙|접수|통과)/.test(joined)) tags.push("장난 섞음");
            if (/(보고 싶|좋아|궁금|설레|만나|갈래)/.test(joined)) tags.push("호감 직접형");
            if (/(괜찮|천천히|부담|편하|나중)/.test(joined)) tags.push("부담 낮춤");
            if (!tags.length) tags.push("무난한 자연체");

            const uniqueTags = [...new Set(tags)].slice(0, 6);
            const profileText = uniqueTags.join(" / ");
            return {
                text: profileText,
                tags: uniqueTags,
                count: myLines.length
            };
        }

        function renderStyleProfile(result) {
            styleProfile = result.text;
            styleProfileTags = result.tags;
            styleSummaryText.textContent = result.count ? `${result.count}개 답장에서 ${result.text} 패턴 잡음.` : `${result.text} 패턴 잡음.`;
            styleTags.innerHTML = "";
            result.tags.forEach((tag) => {
                const chip = document.createElement("span");
                chip.className = "style-tag";
                chip.textContent = tag;
                styleTags.appendChild(chip);
            });
            styleSummary.classList.remove("is-empty");
            updateBrief();
        }

        function syncStyleProfile({ silent = false } = {}) {
            saveCurrentStyleAnswer({ silent: true });
            const samples = cleanStyleSamples();
            if (!samples) {
                if (!silent) {
                    showToast(currentMode === "work" ? "내 회신을 먼저 한 줄 써줘." : "내 답장을 먼저 한 줄 써줘.");
                    fields.styleAnswer.focus();
                }
                return false;
            }
            renderStyleProfile(analyzeVoice(samples));
            clearRecommendation();
            if (!silent) showToast("말투 싱크 완료. 이제 AI 티 좀 빠짐.");
            return true;
        }

        function resetStyleProfile() {
            styleProfile = "";
            styleProfileTags = [];
            styleAnswers = [];
            stylePromptIndex = 0;
            fields.styleAnswer.value = "";
            fields.styleSamples.value = "";
            styleSummary.classList.add("is-empty");
            styleTags.innerHTML = "";
            renderStylePrompt();
            clearRecommendation();
        }

        function resetConference({ keepPanel = false } = {}) {
            chatMessages = [];
            contextSummary = "";
            renderChat();
            renderContextChip();
            if (!keepPanel) conferencePanel.classList.add("is-empty");
        }

        function firstConferenceMessage() {
            return { role: "assistant", text: currentConfig().conference.first };
        }

        function renderContextChip() {
            if (!contextSummary) {
                contextChip.classList.remove("is-on");
                contextChip.textContent = "";
                return;
            }
            contextChip.textContent = `맥락 반영중 · ${contextSummary}`;
            contextChip.classList.add("is-on");
        }

        function renderChat() {
            chatLog.innerHTML = "";
            chatMessages.forEach((message) => {
                const bubble = document.createElement("div");
                bubble.className = `chat-bubble ${message.role === "user" ? "user" : "assistant"}`;
                bubble.textContent = message.text;
                chatLog.appendChild(bubble);
            });
            chatLog.scrollTop = chatLog.scrollHeight;
        }

        function openConference() {
            const config = currentConfig().conference;
            conferenceTitle.textContent = config.title;
            conferenceHint.textContent = config.hint;
            conferenceToggle.textContent = contextSummary ? "작전 회의 다시 열기" : config.open;
            chatInput.placeholder = config.placeholder;
            contextRegenerate.textContent = config.regenerate;
            conferencePanel.classList.remove("is-empty");
            if (!chatMessages.length) {
                chatMessages = [firstConferenceMessage()];
            }
            renderChat();
            renderContextChip();
            window.setTimeout(() => conferencePanel.scrollIntoView({ behavior: "smooth", block: "start" }), 60);
        }

        function closeConference() {
            conferencePanel.classList.add("is-empty");
        }

        function localChatReply(text) {
            const trimmed = text.trim();
            if (currentMode === "work") {
                contextSummary = [contextSummary, trimmed].filter(Boolean).join(" / ").slice(0, 220);
                return "오케이. 그러면 기한이랑 책임 범위가 핵심이네. 이 맥락으로 다시 정리하면 훨씬 덜 위험함.";
            }
            contextSummary = [contextSummary, trimmed].filter(Boolean).join(" / ").slice(0, 220);
            return "오케이, 이건 그냥 답장 문제가 아니라 온도 조절 문제네. 이 맥락으로 다시 짜면 더 자연스러움.";
        }

        function resetChatInputHeight() {
            chatInput.value = "";
            chatInput.style.height = "auto";
        }

        function isDuplicateTailSend(text, now = Date.now()) {
            return Boolean(
                text
                && lastChatSubmitText
                && now - lastChatSubmitAt < 1400
                && text.length <= 2
                && lastChatSubmitText.endsWith(text)
            );
        }

        function pushAssistantMessage(text) {
            const clean = (text || "").trim();
            if (!clean) return;
            const last = chatMessages[chatMessages.length - 1];
            if (last?.role === "assistant" && last.text === clean) return;
            chatMessages.push({ role: "assistant", text: clean });
        }

        async function sendConferenceMessage() {
            const text = chatInput.value.trim();
            if (!text) {
                chatInput.focus();
                return;
            }
            if (isDuplicateTailSend(text)) {
                resetChatInputHeight();
                return;
            }
            if (chatBusy) return;

            chatBusy = true;
            chatSend.disabled = true;
            lastChatSubmitText = text;
            lastChatSubmitAt = Date.now();
            chatMessages.push({ role: "user", text });
            resetChatInputHeight();
            renderChat();

            try {
                const response = await fetch("/api/chat", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        ...profile(),
                        message: cleanInput(),
                        messages: chatMessages,
                        contextSummary
                    })
                });
                if (!response.ok) throw new Error("chat failed");
                const result = await response.json();
                if (!result.reply) throw new Error("bad chat response");
                contextSummary = result.contextSummary || contextSummary;
                pushAssistantMessage(result.reply);
            } catch (error) {
                pushAssistantMessage(localChatReply(text));
            } finally {
                chatBusy = false;
                chatSend.disabled = false;
                renderChat();
                renderContextChip();
                updateBrief();
            }
        }

        function lead(data, style) {
            const input = cleanInput();
            if (!input || input === "오늘 뭐해?") return "";

            if (style === "safe") return `“${input}”에는 너무 길게 설명하지 말고, `;
            if (style === "bounce") return `방금 톡은 일단 좋게 해석하고, `;
            if (style === "flirt") return `“${input}” 이 흐름이면 살짝 여지를 두고, `;
            return `이 톡은 과감하게 받으면, `;
        }

        function tuneReply(text, data, style) {
            if (data.mode === "work") {
                let result = text;
                if (data.contact === "urgent" && style === "short") {
                    result = result.replace("확인했습니다.", "확인했습니다. 바로 보겠습니다.");
                }
                if (data.contact === "soft" && style === "firm") {
                    result = result.replace("어렵습니다", "어려울 것 같습니다");
                }
                if (data.relation === "client" && !result.startsWith("네") && style !== "sense") {
                    result = `네, ${result}`;
                }
                return result;
            }

            let result = lead(data, style) + text;

            if (data.relation === "fading" && style !== "safe") {
                result += " 답장 텀은 바로 말고 살짝 두자.";
            }
            if (data.relation === "ex") {
                result = result.replace("보고 싶어졌는데", "한번 얘기해보고 싶긴 한데");
                result = result.replace("설레도 되는", "좋게 봐도 되는");
            }
            if (data.contact === "dry" && !result.endsWith("?")) {
                result += " 너는?";
            }
            if (data.contact === "slow" && style === "spicy") {
                result = result.replace("맞지?", "아니면 말고.");
            }
            return result;
        }

        function applyVoiceStyle(text, data) {
            if (!data.styleProfile) return text;
            let result = text;
            if (data.styleProfile.includes("짧게 침") && result.length > 42) {
                result = result.split(/[.!?]/)[0].trim();
                if (!/[.!?]$/.test(result)) result += data.mode === "work" ? "." : "";
            }
            if (data.mode === "date" && data.styleProfile.includes("웃음 자주") && !/ㅋ|ㅎ/.test(result)) {
                result += "ㅋㅋ";
            }
            if (data.mode === "date" && data.styleProfile.includes("툭 치는 말끝")) {
                result = result.replace("하고 있어?", "하는 중?").replace("할래?", "갈래?");
            }
            if (data.mode === "work" && data.styleProfile.includes("존댓말 기반") && !/(요|니다|드립니다|세요)[.!?…~]*$/.test(result)) {
                result = result.replace(/다\\.?$/, "드립니다.");
            }
            return result;
        }

        function removeAiSmell(text, data) {
            let result = text
                .replace("좋은 하루 보내", "일단 이렇게 가자")
                .replace("편할 때 답장해", "가능하면 답 줘")
                .replace("도움이 되었으면 좋겠습니다", "이 정도면 될 듯합니다");
            if (data.mode === "date") {
                result = result.replace("오늘은 그냥", "오늘은").replace("시간 맞으면", "각 맞으면");
            }
            return result;
        }

        function applyLocalAdjust(text, data, style) {
            if (["mytone", "more_me"].includes(data.adjust)) return applyVoiceStyle(text, data);
            if (data.adjust === "no_ai") return applyVoiceStyle(removeAiSmell(text, data), data);
            if (data.adjust === "less_cringe") return text.replace("설레도 되는", "좋게 봐도 되는").replace("보고 싶어졌는데", "한번 보고 싶은데");
            if (!data.adjust) return text;
            if (data.mode === "work") {
                if (data.adjust === "short") return text.split(".")[0].trim() + ".";
                if (data.adjust === "polite" && !text.startsWith("네")) return `네, ${text}`;
                if (data.adjust === "safe") return text.replace("진행하겠습니다", "가능 범위 확인 후 진행하겠습니다").replace("제가 잡고", "확인 가능한 범위에서 잡고");
                if (data.adjust === "deadline" && !/(오늘|내일|오전|오후|까지)/.test(text)) return `${text} 가능하시면 오늘 중 확인 부탁드립니다.`;
                return text;
            }

            if (data.adjust === "soft") return text.replace("매달려", "기대하는").replace("과감하게", "가볍게");
            if (data.adjust === "witty" && !text.includes("ㅋㅋ")) return `${text} ㅋㅋ`;
            if (data.adjust === "flirt" && !text.includes("너")) return `${text} 근데 너 톡은 좀 반칙.`;
            if (data.adjust === "spicy") return text.replace("괜찮", "꽤 괜찮").replace("할래?", "할래, 아니면 내가 의미부여 멈출까?");
            if (data.adjust === "calm") return text.replace("보고 싶어졌는데", "시간 맞으면 보고 싶은데").replace("기대하게", "궁금하게");
            return text;
        }

        function predictedNext(item, data) {
            if (item.next) return item.next;
            if (data.mode === "work") {
                if (item.tag === "단호") return "상대가 범위나 일정부터 다시 확인할 가능성이 높음.";
                if (item.tag === "간결") return "확인/요청사항만 짧게 되돌아올 확률이 높음.";
                return "상대가 다음 액션을 바로 잡기 쉬운 흐름.";
            }
            if (item.tag === "매운맛") return "상대가 웃거나 살짝 떠보는 답으로 받을 가능성.";
            if (item.tag === "살짝 플러팅") return "분위기가 괜찮으면 장난 섞인 답이 돌아올 수 있음.";
            if (item.tag === "통통") return "대화가 가볍게 이어질 확률이 높음.";
            return "부담은 낮고 무난하게 답이 올 가능성.";
        }

        function localWarning(data) {
            const draft = data.draft || "";
            if (!draft) {
                return {
                    level: "ok",
                    title: data.mode === "work" ? "초안 없음" : "독 없음",
                    text: data.mode === "work" ? "보내려던 문장이 없어서 회신 위험도는 낮게 봄." : "초안이 없어서 일단 안전. 이제 말맛만 고르면 됨."
                };
            }

            const dateDanger = /(왜|읽씹|서운|화났|짜증|뭐야|ㅡㅡ|\\?\\?)/;
            const workDanger = /(빨리|왜|제 책임|알아서|안 되나요|곤란|문제)/;
            const danger = data.mode === "work" ? workDanger.test(draft) : dateDanger.test(draft);
            if (danger) {
                return {
                    level: "watch",
                    title: data.mode === "work" ? "말끝 조심" : "이건 잠깐 멈춤",
                    text: data.mode === "work" ? "초안에 압박감이 보여서 책임/기한을 더 차분히 나누는 게 좋음." : "초안이 상대를 몰아붙이는 느낌이 있어서 여유를 조금 넣는 게 좋음."
                };
            }
            return {
                level: "ok",
                title: data.mode === "work" ? "보내도 무난" : "나쁘지 않음",
                text: data.mode === "work" ? "초안 자체는 괜찮고, 업무 범위만 더 선명하게 다듬으면 됨." : "초안 위험도는 낮음. 말맛만 조금 더 살리면 됨."
            };
        }

        function updateBrief(data = profile()) {
            if (data.mode === "work") {
                briefRelation.textContent = `${labels[data.relation]} · ${labels[data.goal]}`;
                briefProfile.textContent = profileHint(data);
                briefRisk.textContent = data.goal === "decline" || data.goal === "boundary" ? "문장 단단히" : data.contact === "followup" ? "기한 명확히" : "무난";
                return;
            }
            briefRelation.textContent = `${labels[data.relation]} · ${labels[data.goal]}`;
            briefProfile.textContent = profileHint(data);
            briefRisk.textContent = data.relation === "ex" || data.goal === "line" ? "속도 조절" : data.contact === "seen" ? "마음 덜 주기" : "리스크 낮음";
        }

        function updateBriefFromAi(brief, data) {
            if (!brief) {
                updateBrief(data);
                return;
            }
            briefRelation.textContent = brief.relation || `${labels[data.relation]} · ${labels[data.goal]}`;
            briefProfile.textContent = brief.profile || profileHint(data);
            briefRisk.textContent = brief.risk || (data.mode === "work" ? "무난" : "리스크 낮음");
        }

        function clearRecommendation() {
            hasRecommendation = false;
            lastResult = null;
            activeResultView = "cards";
            replies.innerHTML = "";
            replies.classList.add("is-empty");
            replies.classList.remove("is-hidden");
            compareView.innerHTML = "";
            compareView.classList.add("is-empty");
            compareView.classList.remove("is-hidden");
            resultTools.classList.add("is-empty");
            conferencePanel.classList.add("is-empty");
            viewButtons.forEach((button) => {
                button.classList.toggle("is-active", button.dataset.view === "cards");
            });
            updateBrief();
        }

        function closeCustomSelects(except = null) {
            document.querySelectorAll(".custom-select.is-open").forEach((select) => {
                if (select === except) return;
                select.classList.remove("is-open");
                select.closest(".panel")?.classList.remove("is-menu-open");
                select.querySelector(".select-button").setAttribute("aria-expanded", "false");
            });
        }

        function chooseCustomOption(select, option) {
            select.dataset.value = option.dataset.value;
            select.querySelector(".select-value").textContent = option.textContent;
            select.querySelectorAll(".select-option").forEach((item) => {
                const selected = item === option;
                item.classList.toggle("is-selected", selected);
                item.setAttribute("aria-selected", selected ? "true" : "false");
            });
            closeCustomSelects();
            clearRecommendation();
        }

        function localRecommendations(data) {
            const config = modes[data.mode];
            const styles = config.styles;
            const base = config.templates[data.goal] || Object.values(config.templates)[0];
            return styles.map((style, index) => {
                const [tag, memo] = config.cardMeta[index];
                const tuned = applyVoiceStyle(tuneReply(base[style], data, style), data);
                return {
                    tag,
                    memo,
                    text: applyLocalAdjust(tuned, data, style),
                    next: predictedNext({ tag }, data)
                };
            });
        }

        function renderWarning(warning, data) {
            const safeWarning = warning || localWarning(data);
            const level = ["ok", "watch", "danger"].includes(safeWarning.level) ? safeWarning.level : "ok";
            warningCard.className = `warning-card ${level}`;
            warningTitle.textContent = level === "ok" ? (safeWarning.title || "초안 점검") : data.mode === "work" ? "그대로는 보류" : "이건 보내지 마";
            warningText.textContent = safeWarning.text || "그대로 보내도 큰 위험은 낮음.";
        }

        function renderToneOptions() {
            toneOptions.innerHTML = currentConfig().toneOptions.map(([value, label]) => (
                `<button class="tone-chip" type="button" data-adjust="${value}">${label}</button>`
            )).join("");
        }

        function renderCompare(items, data) {
            compareView.innerHTML = "";
            items.slice(0, 4).forEach((item) => {
                const card = document.createElement("button");
                const tag = document.createElement("strong");
                const body = document.createElement("p");
                const memo = document.createElement("small");
                const next = document.createElement("small");
                const text = item.text || "";

                card.className = "compare-card";
                tag.textContent = item.tag || "답장";
                body.textContent = text;
                memo.textContent = item.memo || "";
                next.textContent = `다음 톡: ${predictedNext(item, data)}`;
                card.append(tag, body, memo, next);
                card.addEventListener("click", () => copyText(text, card));
                compareView.appendChild(card);
            });
            compareView.classList.remove("is-empty");
        }

        function setResultView(view) {
            activeResultView = view;
            viewButtons.forEach((button) => {
                button.classList.toggle("is-active", button.dataset.view === view);
            });
            if (!hasRecommendation) return;
            replies.classList.toggle("is-hidden", view !== "cards");
            compareView.classList.toggle("is-hidden", view !== "compare");
        }

        function renderRecommendations(items, data, brief = null, warning = null) {
            hasRecommendation = true;
            lastResult = { items, data, brief, warning };
            resultTools.classList.remove("is-empty");
            copy.toneTitle.textContent = currentConfig().toneTitle;
            conferenceToggle.textContent = contextSummary ? "작전 회의 다시 열기" : currentConfig().conference.open;
            renderWarning(warning, data);
            renderToneOptions();
            renderCompare(items, data);
            replies.innerHTML = "";
            replies.classList.remove("is-empty");
            replies.classList.remove("is-hidden");
            items.slice(0, 4).forEach((item, index) => {
                const button = document.createElement("button");
                const text = item.text || "";
                const state = document.createElement("span");
                const tag = document.createElement("strong");
                const body = document.createElement("p");
                const next = document.createElement("div");
                const memo = document.createElement("small");

                button.className = "reply";
                button.style.animationDelay = `${index * 70}ms`;
                state.className = "reply-copy-state";
                state.textContent = "복사됨";
                tag.textContent = item.tag || "답장";
                body.textContent = text;
                next.className = "reply-next";
                next.textContent = `다음 톡 예측 · ${predictedNext(item, data)}`;
                memo.textContent = item.memo || "";
                button.append(state, tag, body, next, memo);
                button.addEventListener("click", () => copyText(text, button));
                replies.appendChild(button);
            });
            setResultView(activeResultView);

            updateBriefFromAi(brief, data);

            composer.classList.remove("is-popping");
            void composer.offsetWidth;
            composer.classList.add("is-popping");
            window.setTimeout(() => {
                resultTools.scrollIntoView({ behavior: "smooth", block: "start" });
            }, 80);
        }

        async function generate(options = {}) {
            if ((fields.styleAnswer.value.trim() || cleanStyleSamples()) && !styleProfile) {
                syncStyleProfile({ silent: true });
            }
            const data = { ...profile(), adjust: options.adjust || "" };
            const payload = { ...data, message: cleanInput() };
            const originalText = roll.textContent;
            roll.disabled = true;
            dice.disabled = true;
            roll.classList.add("is-loading");
            roll.textContent = options.adjust ? "톤 다시 굴리는 중..." : currentConfig().loading;
            document.querySelectorAll(".tone-chip").forEach((button) => {
                button.disabled = true;
                button.classList.add("is-busy");
            });

            try {
                const response = await fetch("/api/replies", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(payload)
                });
                if (!response.ok) throw new Error("AI request failed");
                const result = await response.json();
                if (!Array.isArray(result.replies)) throw new Error("Bad AI response");
                renderRecommendations(result.replies, data, result.brief, result.warning);
            } catch (error) {
                renderRecommendations(localRecommendations(data), data, null, localWarning(data));
                showToast("AI가 잠깐 삐끗해서 예비 작전으로 보여줄게.");
            } finally {
                roll.disabled = false;
                dice.disabled = false;
                roll.classList.remove("is-loading");
                roll.textContent = modes[currentMode].rollText || originalText;
                document.querySelectorAll(".tone-chip").forEach((button) => {
                    button.disabled = false;
                    button.classList.remove("is-busy");
                });
            }
        }

        function setActive(button) {
            const group = button.closest(".chips");
            group.querySelectorAll(".chip").forEach((chip) => chip.classList.remove("is-active"));
            button.classList.add("is-active");
            clearRecommendation();
        }

        function randomize() {
            ["relation", "contact", "goal"].forEach((groupName) => {
                const group = document.querySelector(`[data-group="${groupName}"]`);
                const chips = [...group.querySelectorAll(".chip")];
                const chip = chips[Math.floor(Math.random() * chips.length)];
                group.querySelectorAll(".chip").forEach((item) => item.classList.remove("is-active"));
                chip.classList.add("is-active");
            });
            clearRecommendation();
        }

        function showToast(message) {
            toast.textContent = message;
            toast.classList.add("is-on");
            window.clearTimeout(showToast.timer);
            showToast.timer = window.setTimeout(() => toast.classList.remove("is-on"), 1800);
        }

        async function copyText(text, source = null) {
            try {
                await navigator.clipboard.writeText(text);
            } catch (error) {
                const ghost = document.createElement("textarea");
                ghost.value = text;
                document.body.appendChild(ghost);
                ghost.select();
                document.execCommand("copy");
                ghost.remove();
            }
            if (source) {
                document.querySelectorAll(".reply.is-copied, .compare-card.is-copied").forEach((card) => {
                    if (card !== source) card.classList.remove("is-copied");
                });
                source.classList.add("is-copied");
                window.clearTimeout(source.copyTimer);
                source.copyTimer = window.setTimeout(() => source.classList.remove("is-copied"), 1600);
            }
            showToast(currentConfig().copyToast);
        }

        function renderChips(groupName, options) {
            const group = fields[groupName];
            group.innerHTML = options.map(([value, label], index) => (
                `<button class="chip${index === 0 ? " is-active" : ""}" data-value="${value}">${label}</button>`
            )).join("");
        }

        function setCustomSelectOptions(name, options) {
            const select = fields[name];
            const [firstValue, firstLabel] = options[0];
            select.dataset.value = firstValue;
            select.querySelector(".select-value").textContent = firstLabel;
            select.querySelector(".select-menu").innerHTML = options.map(([value, label], index) => (
                `<button class="select-option${index === 0 ? " is-selected" : ""}" type="button" role="option" aria-selected="${index === 0 ? "true" : "false"}" data-value="${value}">${label}</button>`
            )).join("");
        }

        function applyMode(mode) {
            if (mode === currentMode && hasAppliedMode) return;
            if (mode !== currentMode) {
                saveModeState(currentMode);
            }
            currentMode = mode;
            const config = currentConfig();
            const state = stateForMode(mode);

            phone.classList.toggle("work-mode", mode === "work");
            document.documentElement.classList.toggle("work-mode", mode === "work");
            document.body.classList.toggle("work-mode", mode === "work");
            copy.modeButtons.forEach((button) => {
                const active = button.dataset.mode === mode;
                button.classList.toggle("is-active", active);
                button.setAttribute("aria-pressed", active ? "true" : "false");
            });

            copy.brandSubtitle.textContent = config.brandSubtitle;
            copy.marquee.forEach((item) => {
                item.textContent = config.marquee;
            });
            copy.heroTitle.innerHTML = config.heroTitle;
            copy.heroStamp.innerHTML = config.heroStamp;
            copy.relationStep.textContent = config.steps[0];
            copy.profileStep.textContent = config.steps[1];
            copy.styleStep.textContent = config.steps[2];
            copy.messageStep.textContent = config.steps[3];
            copy.relationTitle.textContent = config.titles.relation;
            copy.profileTitle.textContent = config.titles.profile;
            copy.styleTitle.textContent = config.titles.style;
            copy.contactTitle.textContent = config.titles.contact;
            copy.messageTitle.textContent = config.titles.message;
            copy.draftTitle.textContent = config.titles.draft;
            copy.goalTitle.textContent = config.titles.goal;
            copy.toneTitle.textContent = config.toneTitle;
            copy.relationHint.textContent = config.hints.relation;
            copy.profileHint.textContent = config.hints.profile;
            copy.styleHint.textContent = config.hints.style;
            copy.mbtiLabel.textContent = config.fieldLabels.mbti;
            copy.ageLabel.textContent = config.fieldLabels.age;
            copy.genderLabel.textContent = config.fieldLabels.gender;
            copy.jobLabel.textContent = config.fieldLabels.job;
            fields.mbti.placeholder = config.placeholders.mbti;
            fields.mbti.maxLength = config.mbtiMax;
            if (mode === "date" && fields.mbti.value.length > config.mbtiMax) {
                fields.mbti.value = fields.mbti.value.slice(0, config.mbtiMax).toUpperCase();
            }
            fields.job.placeholder = config.placeholders.job;
            fields.message.placeholder = config.placeholders.message;
            fields.draft.placeholder = config.placeholders.draft;
            fields.styleAnswer.placeholder = config.placeholders.styleAnswer;
            conferenceTitle.textContent = config.conference.title;
            conferenceHint.textContent = config.conference.hint;
            conferenceToggle.textContent = config.conference.open;
            chatInput.placeholder = config.conference.placeholder;
            contextRegenerate.textContent = config.conference.regenerate;
            roll.textContent = config.rollText;

            renderChips("relation", config.options.relation);
            renderChips("contact", config.options.contact);
            renderChips("goal", config.options.goal);
            setCustomSelectOptions("age", config.selects.age);
            setCustomSelectOptions("gender", config.selects.gender);
            applyActiveChip("relation", state.relation);
            applyActiveChip("contact", state.contact);
            applyActiveChip("goal", state.goal);
            applyCustomSelectValue("age", state.age);
            applyCustomSelectValue("gender", state.gender);

            fields.mbti.value = mode === "date" ? (state.mbti || "").slice(0, config.mbtiMax).toUpperCase() : state.mbti || "";
            fields.job.value = state.job || "";
            fields.message.value = state.message || config.placeholders.defaultMessage;
            fields.draft.value = state.draft || "";
            styleAnswers = [...(state.styleAnswers || [])];
            stylePromptIndex = state.stylePromptIndex || 0;
            fields.styleAnswer.value = state.styleCurrentAnswer || styleAnswers[stylePromptIndex] || "";
            fields.styleSamples.value = state.styleSamples || buildStyleSamples();
            styleProfile = state.styleProfile || "";
            styleProfileTags = [...(state.styleProfileTags || [])];
            chatMessages = cloneMessages(state.chatMessages || []);
            contextSummary = state.contextSummary || "";
            chatInput.value = "";
            [fields.message, fields.draft, fields.styleAnswer, chatInput].forEach((field) => {
                field.style.height = "auto";
            });
            renderStylePrompt();
            renderStoredStyleProfile();
            renderChat();
            renderContextChip();
            closeCustomSelects();
            clearRecommendation();
            hasAppliedMode = true;
        }

        document.querySelectorAll(".chips").forEach((group) => {
            group.addEventListener("click", (event) => {
                const chip = event.target.closest(".chip");
                if (!chip) return;
                setActive(chip);
            });
        });

        document.querySelectorAll(".custom-select").forEach((select) => {
            select.addEventListener("click", (event) => {
                const option = event.target.closest(".select-option");
                const trigger = event.target.closest(".select-button");
                if (option) {
                    event.stopPropagation();
                    chooseCustomOption(select, option);
                    return;
                }
                if (trigger) {
                    event.stopPropagation();
                    const willOpen = !select.classList.contains("is-open");
                    closeCustomSelects(select);
                    select.classList.toggle("is-open", willOpen);
                    select.closest(".panel")?.classList.toggle("is-menu-open", willOpen);
                    trigger.setAttribute("aria-expanded", willOpen ? "true" : "false");
                }
            });
        });

        document.addEventListener("click", () => closeCustomSelects());
        document.addEventListener("keydown", (event) => {
            if (event.key === "Escape") closeCustomSelects();
        });

        [fields.mbti, fields.job, fields.message, fields.draft].forEach((field) => {
            field.addEventListener("input", clearRecommendation);
            field.addEventListener("change", clearRecommendation);
        });

        fields.mbti.addEventListener("input", () => {
            if (currentMode === "date") {
                fields.mbti.value = fields.mbti.value.toUpperCase();
            }
        });

        fields.message.addEventListener("input", () => {
            fields.message.style.height = "auto";
            fields.message.style.height = `${fields.message.scrollHeight}px`;
        });

        fields.draft.addEventListener("input", () => {
            fields.draft.style.height = "auto";
            fields.draft.style.height = `${fields.draft.scrollHeight}px`;
        });

        fields.styleAnswer.addEventListener("input", () => {
            styleProfile = "";
            styleProfileTags = [];
            styleSummary.classList.add("is-empty");
            fields.styleAnswer.style.height = "auto";
            fields.styleAnswer.style.height = `${fields.styleAnswer.scrollHeight}px`;
            clearRecommendation();
        });

        styleNext.addEventListener("click", nextStylePrompt);
        styleSync.addEventListener("click", () => syncStyleProfile());
        styleClear.addEventListener("click", resetStyleProfile);
        conferenceToggle.addEventListener("click", openConference);
        conferenceClose.addEventListener("click", closeConference);

        chatInput.addEventListener("input", () => {
            chatInput.style.height = "auto";
            chatInput.style.height = `${chatInput.scrollHeight}px`;
        });

        chatInput.addEventListener("compositionstart", () => {
            chatInputComposing = true;
        });

        chatInput.addEventListener("compositionend", () => {
            chatInputComposing = false;
        });

        chatInput.addEventListener("keydown", (event) => {
            if (event.key === "Enter" && !event.shiftKey) {
                if (event.isComposing || chatInputComposing || event.keyCode === 229) return;
                event.preventDefault();
                sendConferenceMessage();
            }
        });

        chatSend.addEventListener("click", sendConferenceMessage);
        contextRegenerate.addEventListener("click", () => {
            if (!contextSummary && chatMessages.length <= 1) {
                showToast("상황 한 줄만 더 털어줘. 그 다음 다시 짜자.");
                chatInput.focus();
                return;
            }
            generate();
        });

        toneOptions.addEventListener("click", (event) => {
            const button = event.target.closest(".tone-chip");
            if (!button) return;
            if (["mytone", "more_me", "no_ai", "less_cringe"].includes(button.dataset.adjust) && (fields.styleAnswer.value.trim() || cleanStyleSamples()) && !styleProfile) {
                syncStyleProfile({ silent: true });
            }
            if (["mytone", "more_me"].includes(button.dataset.adjust) && !styleProfile) {
                showToast("내 답장 한 줄 쓰고 먼저 싱크해줘.");
                fields.styleAnswer.focus();
                return;
            }
            generate({ adjust: button.dataset.adjust });
        });

        viewButtons.forEach((button) => {
            button.addEventListener("click", () => setResultView(button.dataset.view));
        });

        roll.addEventListener("click", () => generate());
        dice.addEventListener("click", randomize);
        copy.modeButtons.forEach((button) => {
            button.addEventListener("click", () => applyMode(button.dataset.mode));
        });

        applyMode("date");
    </script>
</body>
</html>"""

    @app.flask.route("/")
    @app.flask.route("/<path:path>")
    def rebound(path=""):
        return html
