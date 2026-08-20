import json
import os
import re
import urllib.request

SECURITY_POLICY_KB = [
    {
        "id": "malware",
        "title": "Malware / executable payload",
        "keywords": ["exe", "dll", "bat", "cmd", "scr", "msi", "ps1", "vbs", "jar", "apk", "macro", "payload"],
        "policy": "Executable, script, and macro-bearing objects are treated as untrusted until inspected and approved.",
    },
    {
        "id": "credentials",
        "title": "Credential and secret leakage",
        "keywords": ["secret", "token", "password", "passwd", "api_key", "accesskey", "aws", "private key", "credential", "oauth"],
        "policy": "Credentials, tokens, and private keys must never be stored or shared without explicit policy approval.",
    },
    {
        "id": "pii",
        "title": "PII / sensitive data exposure",
        "keywords": ["ssn", "employee_salary", "tax", "passport", "national id", "credit card", "medical", "confidential", "pii"],
        "policy": "Financial, personal, or regulated data requires a higher trust threshold and must remain behind strict access controls.",
    },
    {
        "id": "url-risk",
        "title": "Malicious URL / phishing pattern",
        "keywords": ["bit.ly", "tinyurl", "download", "verify", "login", "urgent", "claim", "free", "suspicious redirect", "phish"],
        "policy": "Shortened, redirect-heavy, or fake-login URLs are treated as suspicious and must be reviewed or blocked.",
    },
    {
        "id": "archive-risk",
        "title": "Archive / compressed payload",
        "keywords": ["zip", "rar", "7z", "cab", "archive", "compressed", "nested", "dump"],
        "policy": "Archives may contain nested malicious content and require recursive inspection before approval.",
    },
    {
        "id": "policy-violation",
        "title": "Policy violation",
        "keywords": ["confidential", "internal", "restricted", "unauthorized sharing", "financial", "gov", "regulated"],
        "policy": "Objects that violate organization policy or external compliance requirements must be reviewed or blocked.",
    },
]


def normalize_text(value):
    return re.sub(r'[^a-z0-9\s\-_]+', ' ', (value or '').lower()).strip()


def retrieve_policy_hits(file_name, file_type, findings):
    combined = " ".join(filter(None, [file_name, file_type, *findings]))
    normalized = normalize_text(combined)

    hits = []
    for rule in SECURITY_POLICY_KB:
        score = 0
        for keyword in rule["keywords"]:
            if keyword in normalized:
                score += 1
        if score:
            hits.append({
                "id": rule["id"],
                "title": rule["title"],
                "score": min(score, 5),
                "policy": rule["policy"],
            })

    return sorted(hits, key=lambda item: item["score"], reverse=True)


def _build_local_rag_report(file_name, file_type, findings, url=None):
    policy_hits = retrieve_policy_hits(file_name, file_type, findings)
    if not policy_hits:
        return {
            "agent_summary": "The local security knowledge base did not find strong policy matches. The object remains within the normal trust baseline.",
            "policy_hits": [],
            "risk_adjustment": 0,
            "recommendations": [
                "Continue standard monitoring and retain the object in the approved storage policy baseline.",
            ],
        }

    risk_adjustment = sum(min(hit["score"], 4) * 8 for hit in policy_hits)
    top_hit = policy_hits[0]
    recommendations = [
        top_hit["policy"],
        "Escalate to a security review when multiple policy categories match the same object.",
        "Keep the file quarantined until a human reviewer validates the final approval decision.",
    ]

    if url:
        recommendations.insert(0, "Validate the destination URL before allowing any fetch, redirect, or file download from the provided link.")

    summary = (
        f"AI Security Agent matched {len(policy_hits)} policy vectors in the trusted knowledge base, "
        f"with the strongest signal being '{top_hit['title']}'. This raises the object risk level and supports a review or block decision."
    )

    return {
        "agent_summary": summary,
        "policy_hits": policy_hits,
        "risk_adjustment": min(risk_adjustment, 40),
        "recommendations": recommendations,
    }


def _call_openai_agent(prompt):
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return None

    model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    payload = {
        "model": model,
        "temperature": 0.2,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are CloudVault Sentinel, a zero-trust cloud security AI agent. "
                    "Return valid JSON with keys: summary, risk_adjustment, recommendations (list of strings), policy_hits (list of objects with id, title, score, policy). "
                    "Be strict, explainable, and favor review or block when policy signals are strong."
                ),
            },
            {"role": "user", "content": prompt},
        ],
    }

    try:
        request = urllib.request.Request(
            "https://api.openai.com/v1/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(request, timeout=20) as response:
            data = json.loads(response.read().decode("utf-8"))
            raw_message = data["choices"][0]["message"]["content"]
            return json.loads(raw_message)
    except Exception:
        return None


def analyze_with_ai_security_agent(file_name, file_type, findings, url=None):
    local_report = _build_local_rag_report(file_name, file_type, findings, url=url)
    retrieval_context = "\n".join(
        [
            f"- {hit['title']}: {hit['policy']} (score={hit['score']})"
            for hit in local_report["policy_hits"]
        ]
    ) or "No explicit matches found in the local knowledge base."

    prompt = (
        f"File name: {file_name}\n"
        f"File type: {file_type}\n"
        f"URL: {url or 'n/a'}\n"
        f"Findings: {json.dumps(findings, ensure_ascii=False)}\n\n"
        "Security policy knowledge base context:\n"
        f"{retrieval_context}\n\n"
        "Evaluate whether this object should be approved, reviewed, or blocked under a zero-trust cloud security policy. "
        "Return actionable, explainable, and evidence-based guidance."
    )

    ai_response = _call_openai_agent(prompt)
    if not ai_response:
        return local_report

    recommendations = ai_response.get("recommendations") or local_report["recommendations"]
    policy_hits = ai_response.get("policy_hits") or local_report["policy_hits"]
    risk_adjustment = int(ai_response.get("risk_adjustment") or local_report["risk_adjustment"])
    summary = ai_response.get("summary") or local_report["agent_summary"]

    return {
        "agent_summary": summary,
        "policy_hits": policy_hits,
        "risk_adjustment": min(max(risk_adjustment, 0), 40),
        "recommendations": recommendations if isinstance(recommendations, list) else local_report["recommendations"],
    }


def generate_rag_security_report(file_name, file_type, findings, url=None):
    return analyze_with_ai_security_agent(file_name, file_type, findings, url=url)
