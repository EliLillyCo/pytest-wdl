import textwrap

from pytest_wdl.executors import ExecutionFailedError


def test_execution_failed_error():
    try:
        raise ExecutionFailedError(
            executor="foo",
            target="target",
            status="Failed",
            inputs={
                "a": 1,
                "b": "bar"
            },
            executor_stdout="dis happen",
            executor_stderr="dis an err\noopsy",
            failed_task="baz",
            failed_task_exit_status=1,
            failed_task_stdout="oh oh\nsomeone set us up the bomb",
            failed_task_stderr="beep boop beep\nI am except"
        )
    except ExecutionFailedError as err:
        assert str(err) == textwrap.dedent(f"""
        foo failed with status Failed while running task baz of target:
            inputs:
                {{'a': 1, 'b': 'bar'}}
            executor_stdout:
                dis happen
            executor_stderr:
                dis an err
                oopsy
            failed_task_exit_status: 1
            failed_task_stdout:
                oh oh
                someone set us up the bomb
            failed_task_stderr:
                beep boop beep
                I am except
        """)
