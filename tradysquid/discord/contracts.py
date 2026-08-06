from __future__ import annotations
import hashlib, json

def validate_payload(payload:dict)->None:
    content=str(payload.get('content',''))
    if len(content)>2000: raise ValueError('Discord content exceeds 2000 characters')
    embeds=payload.get('embeds',[])
    if len(embeds)>10: raise ValueError('Discord payload exceeds 10 embeds')
    total=0
    for embed in embeds:
        total += len(str(embed.get('title','')))+len(str(embed.get('description','')))
        fields=embed.get('fields',[])
        if len(fields)>25: raise ValueError('Discord embed exceeds 25 fields')
        total += sum(len(str(f.get('name','')))+len(str(f.get('value',''))) for f in fields)
    if total>6000: raise ValueError('Discord embed text exceeds 6000 characters')

def signature(payload:dict)->str:
    validate_payload(payload)
    return hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def split_text(text:str,limit:int=1900)->list[str]:
    if limit<100: raise ValueError('limit too small')
    chunks=[]; current=''
    for line in text.splitlines() or ['']:
        proposed=line if not current else current+'\n'+line
        if len(proposed)<=limit: current=proposed
        else:
            if current: chunks.append(current)
            while len(line)>limit: chunks.append(line[:limit]); line=line[limit:]
            current=line
    if current or not chunks: chunks.append(current)
    return chunks
