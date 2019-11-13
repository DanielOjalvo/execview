



class ExecError(Exception):
    '''
    Basic exception
    '''
    def __init__(self, msg = None):
        if msg is None:
            # default error message
            msg = "Error occured."
        super(ExecError, self).__init__(msg)
        
