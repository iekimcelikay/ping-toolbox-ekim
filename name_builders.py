"""
I'M NOT SURE IF CLASS STRUCTURE IS NECESSARY HERE.
MAY REFACTOR INTO FUNCTIONS LATER (07/05/26)
"""
class NameBuilderRegistry:
    """Central registry for all model name builders."""

    def __init__(self):
        self._builders = {}

    def register(self, model_name):
        """Decorator to register a model name builder function."""
        def decorator(builder_func):
            self._builders[model_name] = builder_func
            return builder_func
        return decorator

    def get(self, model_name):
        """Retrieve a registered model name builder function."""
        if model_name not in self._builders:
            raise ValueError(f"Unknown model: {model_name}."
                             f"Available: {list(self._builders.keys())}")
        return self._builders[model_name]

    def list_models(self):
        """List all registered model names."""
        return list(self._builders.keys())


# Global registry instance
name_builders = NameBuilderRegistry

# Register builders with decarator
@name_builders.register("cochlea_zilany2014")
def cochlea_zilany2014_name_builder(params, timestamp):
    num_runs = params['num_runs']
    num_cf = params['num_cf']
    min_cf = params['min_cf']
    max_cf = params['max_cf']
    return (f"cochlea_zilany2014_psth_batch_"
            f"{num_runs}runs_{num_cf}cfs_{min_cf}-{max_cf}Hz_{timestamp}")