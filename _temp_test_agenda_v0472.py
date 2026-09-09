from pathlib import Path
import ast
from datetime import datetime, timedelta

SRC=Path('source/gph_central.py')
BASE=Path('/tmp/gph_before_agenda_v0472.py')
before=BASE.read_text(encoding='utf-8')
after=SRC.read_text(encoding='utf-8')

assert 'APP_VERSION = "0.47.2"' in after


def db_class(source):
    tree=ast.parse(source)
    for node in tree.body:
        if isinstance(node,ast.ClassDef) and node.name=='Database':
            return node
    raise AssertionError('Database ausente')


def method_map(cls):
    return {
        n.name: ast.dump(n,include_attributes=False)
        for n in cls.body
        if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))
    }

bmap=method_map(db_class(before))
amap=method_map(db_class(after))
allowed={'_is_operational_draw','_reset_expected_target','_operational_schedule_for_date'}
assert bmap.keys()==amap.keys(), 'conjunto de métodos Database mudou'
changed={name for name in bmap if bmap[name]!=amap[name]}
assert changed==allowed, f'métodos Database alterados além da agenda: {sorted(changed)}'
print('OK: somente 3 métodos de agenda do Database foram alterados')

# Monta uma classe mínima diretamente a partir dos 3 métodos novos.
cls_after=db_class(after)
nodes={n.name:n for n in cls_after.body if isinstance(n,ast.FunctionDef)}
parts=['class AgendaTeste:']
for name in ('_is_operational_draw','_operational_schedule_for_date','_reset_expected_target'):
    seg=ast.get_source_segment(after,nodes[name])
    parts.extend('    '+line for line in seg.splitlines())
namespace={'datetime':datetime,'timedelta':timedelta}
exec('\n'.join(parts),namespace)
A=namespace['AgendaTeste']()

wed='2026-09-09'
sat='2026-09-12'
sun='2026-09-13'
mon='2026-09-14'
tue='2026-09-08'
assert datetime.strptime(wed,'%Y-%m-%d').weekday()==2
assert datetime.strptime(sun,'%Y-%m-%d').weekday()==6

assert A._operational_schedule_for_date(wed)==[
    ('PPT','09:00'),('PTM','11:00'),('PT','14:00'),('PTV','16:00'),('FEDERAL','20:00'),('CORUJA','21:00')
]
assert ('PTN','18:00') not in A._operational_schedule_for_date(wed)
assert A._reset_expected_target({'data':wed,'sorteio':'PTV','hora':'16:00'})=={
    'data':wed,'sorteio':'FEDERAL','hora':'20:00','derived':True
}
assert A._reset_expected_target({'data':wed,'sorteio':'FEDERAL','hora':'20:00'})=={
    'data':wed,'sorteio':'CORUJA','hora':'21:00','derived':True
}
assert A._reset_expected_target({'data':wed,'sorteio':'CORUJA','hora':'21:00'})=={
    'data':'2026-09-10','sorteio':'PPT','hora':'09:00','derived':True
}
assert A._is_operational_draw({'data':wed,'sorteio':'FEDERAL'}) is True
assert A._is_operational_draw({'data':wed,'sorteio':'PTN'}) is False
print('OK: quarta PTV 16h -> Federal 20h -> Coruja 21h, sem PTN 18h')

assert A._operational_schedule_for_date(sat)==[
    ('PPT','09:00'),('PTM','11:00'),('PT','14:00'),('PTV','16:00'),('CORUJA','21:00')
]
assert A._reset_expected_target({'data':sat,'sorteio':'CORUJA','hora':'21:00'})=={
    'data':sun,'sorteio':'FEDERAL','hora':'11:00','derived':True
}
print('OK: sábado permanece sem 18h e avança para Federal de domingo 11h')

assert A._operational_schedule_for_date(sun)==[
    ('FEDERAL','11:00'),('PT','14:00'),('PTV','16:00')
]
assert A._reset_expected_target({'data':sun,'sorteio':'FEDERAL','hora':'11:00'})=={
    'data':sun,'sorteio':'PT','hora':'14:00','derived':True
}
assert A._reset_expected_target({'data':sun,'sorteio':'PTV','hora':'16:00'})=={
    'data':mon,'sorteio':'PPT','hora':'09:00','derived':True
}
assert A._is_operational_draw({'data':sun,'sorteio':'FEDERAL'}) is True
assert A._is_operational_draw({'data':sun,'sorteio':'PTM'}) is False
assert A._is_operational_draw({'data':sun,'sorteio':'PT'}) is True
assert A._is_operational_draw({'data':sun,'sorteio':'PTV'}) is True
print('OK: domingo Federal 11h -> PT 14h -> PTV 16h')

normal=A._operational_schedule_for_date(tue)
assert ('PTN','18:00') in normal and all(name!='FEDERAL' for name,_ in normal)
assert A._reset_expected_target({'data':tue,'sorteio':'PTV','hora':'16:00'})=={
    'data':tue,'sorteio':'PTN','hora':'18:00','derived':True
}
print('OK: terça mantém PTN 18h normalmente')

# Garante que os consumidores continuam apontando para a agenda centralizada.
for required in ('def next_operational_target','def is_next_operational_target','def possible_operational_gaps'):
    assert required in after
assert 'self._operational_schedule_for_date(iso)' in after
print('OK: próxima rodada/lacunas continuam consumindo a agenda central')
