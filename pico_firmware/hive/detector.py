class Detector:
	"""
	Detector metaclass.
	"""
	def Construct(baseobject, *args, **kwargs, configure=None, read=None):
		
		if configure == None:
			configure = lambda *args, **kwargs: None
		if read == None:
			read = lambda *args, **kwargs: None

		detector = type(f"<Detector-{baseobject.__class__}>", (type(baseobject,)), {"configure": configure, "read": read})
		
		## Create the detector
		return detector