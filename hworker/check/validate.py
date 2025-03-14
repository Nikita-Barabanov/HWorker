"""Tasks meta-information checks and check results"""

from datetime import datetime
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

from ..config import get_check_directory, get_validator_name, get_version_validator_name, get_task_info
from ..depot import store, search
from ..depot.objects import Check, Solution, CheckResult, CheckCategoryEnum, VerdictEnum, Criteria
from ..log import get_logger
from ._tools import get_result_ID


def validate_wo_store(validator: Check, solution: Solution, check_num: int = 0) -> CheckResult:
    """Runs validator on a given solution and returns result object

    :param validator:
    :param solution:
    :param check_num:
    :return:
    """
    # TODO: add check nums for parallel work
    validator_args = []
    for name in solution.checks:
        if name == validator.ID:
            validator_args = get_task_info(validator.TASK_ID).get(validator.ID, [])

    name, b = list(validator.content.items())[0]
    module_path = Path(get_check_directory()) / name
    with open(module_path, "wb") as m:
        m.write(b)

    spec = spec_from_file_location(name.rpartition(".")[0], module_path)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)

    validator_type = (set(dir(module)) & {get_validator_name(), get_version_validator_name()} or {None}).pop()
    stderr, result = b"", 0.0

    if validator_type:
        v = getattr(module, validator_type)
        try:
            if validator_type == get_validator_name():
                result = v(solution, *validator_args)
            else:
                result = v(search(Solution, Criteria("ID", "==", solution.ID)), *validator_args)
        except Exception as error:
            get_logger(__name__).warning(f"Validator {validator.ID} crashed on {solution.ID} solution:\n {error}")
            stderr = str(error).encode()
        finally:
            module_path.unlink(missing_ok=True)
        verdict = VerdictEnum.passed if not stderr else VerdictEnum.failed
    else:
        verdict = VerdictEnum.missing

    return CheckResult(
        ID=get_result_ID(validator, solution),
        USER_ID=solution.USER_ID,
        TASK_ID=solution.TASK_ID,
        timestamp=datetime.now().timestamp(),
        rating=result,
        category=validator.category,
        stdout=b"",
        stderr=stderr,
        check_ID=validator.ID,
        check_timestamp=validator.timestamp,
        solution_ID=solution.ID,
        solution_timestamp=solution.timestamp,
        verdict=verdict,
    )


def validate(validator: Check, solution: Solution, check_num: int = 0) -> None:
    """Runs validator on a given solution and save the result

    :param validator:
    :param solution:
    :param check_num:
    :return:
    """
    get_logger(__name__).debug(f"Checking solution {solution.ID} with {validator.ID} validator")
    if validator.category == CheckCategoryEnum.validate:
        result = validate_wo_store(validator, solution, check_num)
        store(result)
    else:
        get_logger(__name__).warning(f"The {validator.ID} object given to validate is not a validator")
