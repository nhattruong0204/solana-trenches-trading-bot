"""LLM prompts for token analysis synthesis."""

SYNTHESIS_PROMPT = """You are generating a token breakdown report for a crypto trading community.

## INPUT DATA
Token Address: {token_address}
Symbol: {symbol}
Name: {name}
Chain: Base (Ethereum L2)

### Contract Analysis
- Deployer Address: {deployer_address}
- Deployer Holding: {deployer_balance_pct:.1f}%
- Is Honeypot: {is_honeypot}
- Has Mint Function: {has_mint_function}
- Has Blacklist: {has_blacklist}
- Owner Renounced: {is_renounced}
- Has Proxy: {has_proxy}
- Deployer Prior Tokens: {deployer_prior_tokens_count}

### Developer Profile
- Twitter: {dev_twitter}
- Followers: {dev_followers}
- Account Age: {dev_account_age_days} days
- Verified: {dev_verified}
- Attribution Verified: {attribution_verified}
- Prior Projects: {prior_projects}
- Red Flags: {red_flags}
- Is Anonymous: {is_anonymous}

### On-Chain Metrics
- FDV: ${fdv:,.0f}
- Market Cap: ${market_cap:,.0f}
- Liquidity: ${liquidity:,.0f}
- 24h Volume: ${volume_24h:,.0f}
- Holders: {holder_count}
- Top 10 Holder %: {top_10_holder_pct:.1f}%
- Token Age: {token_age_hours:.1f} hours
- Price Change 24h: {price_change_24h:+.1f}%

## TASK
Generate exactly 3-5 PROs and 2-4 CONs for this token.

## RULES
1. Each point MUST be factual and based on the data provided above
2. Each point should be concise (one sentence)
3. Include source attribution in parentheses when possible
4. Do NOT hallucinate or make up information
5. If you can't verify something, explicitly say "unverified"
6. Focus on what traders care about: risk, opportunity, and credibility

## OUTPUT FORMAT
Return ONLY valid JSON in this exact format:
{{
    "pros": [
        {{"text": "Point text here", "confidence": 0.95, "source": "data source"}},
        ...
    ],
    "cons": [
        {{"text": "Point text here", "confidence": 0.85, "source": "data source"}},
        ...
    ],
    "overall_assessment": "One sentence summary",
    "confidence_score": 0.75
}}
"""

FACT_CHECK_PROMPT = """You are a fact-checker for crypto token analysis reports.

## ORIGINAL REPORT
{report_json}

## RAW DATA
{raw_data_json}

## TASK
Verify each claim in the report against the raw data. Flag any:
1. Claims that cannot be verified from the data
2. Claims that contradict the data
3. Exaggerated or misleading statements
4. Missing important risk factors

## OUTPUT FORMAT
Return JSON:
{{
    "verified_claims": ["claim1", "claim2"],
    "unverified_claims": ["claim3"],
    "contradictions": ["claim4 contradicts X"],
    "missing_risks": ["important risk not mentioned"],
    "overall_accuracy": 0.85
}}
"""

RISK_RATING_PROMPT = """Based on the following token data, determine the appropriate risk rating.

## DATA
{data_summary}

## RATING CRITERIA

GREEN (Low Risk):
- Liquidity > $50,000
- Top 10 holders < 10%
- Dev verified or well-known
- No honeypot indicators
- Contract renounced or audited
- Token age > 24 hours

YELLOW (Moderate Risk):
- Liquidity $10,000-$50,000
- Top 10 holders 10-20%
- Some dev information available
- No major red flags
- Token age 6-24 hours

ORANGE (High Risk):
- Liquidity $5,000-$10,000
- Top 10 holders 20-30%
- Anonymous dev
- Early stage (<6 hours)
- Some concerning signals

RED (Avoid):
- Honeypot detected
- Known scammer dev
- Top 10 holders > 30%
- Liquidity < $5,000
- Multiple red flags
- Contract has dangerous functions

## OUTPUT
Return JSON:
{{
    "rating": "green|yellow|orange|red",
    "primary_reason": "Main reason for this rating",
    "secondary_factors": ["factor1", "factor2"],
    "confidence": 0.85
}}
"""

# Template for the final Telegram message
TELEGRAM_MESSAGE_TEMPLATE = """{risk_emoji} ${symbol} - ${fdv_display} FDV

Dev: {dev_link}

Pros:
{pros_formatted}

Cons:
{cons_formatted}

Contract: `{contract_address}`
{dexscreener_url}"""

# Formatting helpers
def format_fdv(fdv: float) -> str:
    """Format FDV for display."""
    if fdv >= 1_000_000_000:
        return f"{fdv / 1_000_000_000:.1f}B"
    elif fdv >= 1_000_000:
        return f"{fdv / 1_000_000:.1f}M"
    elif fdv >= 1_000:
        return f"{fdv / 1_000:.1f}K"
    else:
        return f"{fdv:.0f}"


def format_pros_cons(items: list, is_pro: bool = True) -> str:
    """Format pros or cons list for Telegram."""
    prefix = "+" if is_pro else "-"
    lines = []
    for item in items:
        if isinstance(item, dict):
            text = item.get("text", str(item))
        else:
            text = str(item)
        lines.append(f"{prefix} {text}")
    return "\n".join(lines)
