class BaseDomainException(Exception):
    """모든 비즈니스 도메인 예외의 기본 클래스"""
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message

class EntityNotFoundException(BaseDomainException):
    """조회하고자 하는 리소스가 존재하지 않을 때"""
    pass

class AlreadyExistsException(BaseDomainException):
    """중복된 리소스 생성 시"""
    pass

class DatabaseOperationException(BaseDomainException):
    """DB 쿼리 중 복구 불가능한 에러 발생 시"""
    pass
