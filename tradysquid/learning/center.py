from __future__ import annotations
class LearningCenter:
    def __init__(self,catalog:dict):
        raw=catalog.get('lessons',[])
        if len(raw)!=27: raise ValueError('Learning Center must contain exactly 27 lessons')
        defaults=catalog.get('lesson_defaults',{})
        self.lessons={}
        for item in raw:
            title=item['title']; lower=title.lower(); lesson={**defaults,**item}
            for source,target in [('purpose_template','purpose'),('concept_template','concept'),('scanner_application_template','scanner_application'),('practice_drill_template','practice_drill')]:
                template=lesson.pop(source,None)
                if template: lesson[target]=template.format(title=lower)
            self.lessons[lesson['lesson_id']]=lesson
    def search(self,query:str)->list[dict]:
        words=[w.lower() for w in query.split() if w]; scored=[]
        for lesson in self.lessons.values():
            hay=' '.join(str(v) for v in lesson.values()).lower(); score=sum(hay.count(w) for w in words)
            if score: scored.append((score,lesson))
        return [x for _,x in sorted(scored,key=lambda pair:(-pair[0],pair[1]['lesson_id']))]
