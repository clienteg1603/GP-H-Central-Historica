import multiprocessing as mp
import queue
import sys
import tempfile
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'source'))
import gph_central as mod


def main():
    db_path=Path(tempfile.mkdtemp())/'worker_test.db'
    db=mod.Database(db_path)
    direct=db.meta_walk_forward(window=20)

    ctx=mp.get_context('spawn')
    q=ctx.Queue(); ev=ctx.Event()
    p=ctx.Process(
        target=mod._meta_walk_forward_process_worker,
        args=(str(db_path),20,q,ev),
        name='GPH-Test-MetaWF',
    )
    p.start()
    result=None; error=None
    deadline=time.time()+30
    while time.time()<deadline and result is None and error is None:
        try:
            msg=q.get(timeout=0.5)
        except queue.Empty:
            if not p.is_alive() and p.exitcode not in (None,0):
                error=f'worker saiu com código {p.exitcode}'
            continue
        if msg[0]=='done': result=msg[1]
        elif msg[0]=='error': error=msg[1]
    if result is None and error is None:
        error='timeout aguardando worker'
    p.join(timeout=3)
    if p.is_alive():
        p.terminate(); p.join(timeout=3)
    q.close()
    assert error is None, error
    assert result is not None
    assert result['simulated_rounds']==direct['simulated_rounds']==0
    assert result['model_version']=='META_LOGIT_NATIVE_V1'
    assert result['brain_frozen'] is True
    assert result['lookahead_safe'] is True
    print('TESTE MULTIPROCESS v0.42.1 OK')


if __name__=='__main__':
    mp.freeze_support()
    main()
