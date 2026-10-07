import json, os, smtplib, ssl, urllib.request
from email.message import EmailMessage
from pathlib import Path

LEAGUE = os.getenv('ESPN_LEAGUE_ID', '1773267264')
SEASON = os.getenv('ESPN_SEASON', '2026')
URL = f'https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/{SEASON}/segments/0/leagues/{LEAGUE}?view=mTeam&view=mMatchupScore&view=mStandings'


def fetch():
    req = urllib.request.Request(URL, headers={'User-Agent': 'Mozilla/5.0 (compatible; FantasyRecap/1.0)', 'Accept': 'application/json'})
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.load(response)


def make_report(data):
    teams = {t['id']: t for t in data['teams']}
    # ESPN advances currentMatchupPeriod to the upcoming week after Monday's games.
    current = int(data['status']['currentMatchupPeriod'])
    week = current - 1
    if week < 1:
        raise ValueError('No completed fantasy week yet')
    games = [g for g in data['schedule'] if g['matchupPeriodId'] == week and g.get('winner') in ('HOME', 'AWAY', 'TIE')]
    if not games:
        raise ValueError(f'No finalized games for week {week}; will not send an incomplete recap')
    lines = [f'ESPN Fantasy Football — Week {week} Recap', '', 'MATCHUPS']
    scores = []
    margins = []
    for g in games:
        home, away = g['home'], g['away']
        hn, an = teams[home['teamId']]['name'], teams[away['teamId']]['name']
        hs, ass = float(home['totalPoints']), float(away['totalPoints'])
        scores.extend([(hn, hs), (an, ass)])
        margins.append((abs(hs-ass), hn, an))
        if g['winner'] == 'TIE':
            lines.append(f'{hn} tied {an}: {hs:.2f}–{ass:.2f}')
        elif g['winner'] == 'HOME':
            lines.append(f'{hn} beat {an}: {hs:.2f}–{ass:.2f}')
        else:
            lines.append(f'{an} beat {hn}: {ass:.2f}–{hs:.2f}')
    if len(scores) != len(teams):
        raise ValueError('Unexpected number of weekly team scores; will not send incomplete recap')
    lines.extend(['', 'TOP 3 SCORERS'])
    lines.extend(f'{i}. {n}: {p:.2f}' for i, (n,p) in enumerate(sorted(scores, key=lambda x:-x[1])[:3],1))
    lines.extend(['', 'BOTTOM 3 SCORERS'])
    lines.extend(f'{i}. {n}: {p:.2f}' for i, (n,p) in enumerate(sorted(scores, key=lambda x:x[1])[:3],1))
    lines.extend(['', 'STANDINGS'])
    ordered = sorted(teams.values(), key=lambda t:(-t['record']['overall']['percentage'], -t['record']['overall']['pointsFor']))
    for i,t in enumerate(ordered,1):
        r=t['record']['overall']
        lines.append(f"{i}. {t['name']} — {r['wins']}-{r['losses']}-{r['ties']} (PF {r['pointsFor']:.2f})")
    closest=min(margins)
    biggest=max(margins)
    lines.extend(['', 'HIGHLIGHTS', f'Closest matchup: {closest[1]} vs {closest[2]} ({closest[0]:.2f} pts)', f'Biggest blowout: {biggest[1]} vs {biggest[2]} ({biggest[0]:.2f} pts)'])
    return week, '\n'.join(lines)


def send_email(week, report):
    sender=os.environ['SMTP_USER']
    password=os.environ['SMTP_APP_PASSWORD']
    recipient=os.environ['REPORT_TO']
    msg=EmailMessage()
    msg['Subject']=f'Fantasy Football — Week {week} Recap'
    msg['From']=sender
    msg['To']=recipient
    msg.set_content(report)
    with smtplib.SMTP_SSL('smtp.gmail.com',465,context=ssl.create_default_context(),timeout=30) as server:
        server.login(sender,password)
        server.send_message(msg)

if __name__=='__main__':
    week, report=make_report(fetch() if not os.getenv('TEST_JSON') else json.loads(Path(os.environ['TEST_JSON']).read_text()))
    print(report)
    if os.getenv('DRY_RUN') != '1':
        send_email(week, report)
