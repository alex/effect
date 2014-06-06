"""
Various functions for inspecting and restructuring effects.
"""

from __future__ import print_function

import sys

from . import Effect, synchronous_performer, perform, default_dispatcher

import six


class StubIntent(object):
    """An effect that returns a pre-specified result."""
    def __init__(self, result):
        self.result = result

    def __repr__(self):
        return "StubIntent(%r)" % (self.result,)

    @synchronous_performer
    def perform_effect(self, dispatcher):
        return self.result


def resolve_effect(effect, result, is_error=False):
    """
    Supply a result for an effect, allowing its callbacks to run.

    The return value of the last callback is returned, unless any callback
    returns another Effect, in which case an Effect representing that
    operation plus the remaining callbacks will be returned.

    This allows you to test your code in a somewhat "channel"-oriented
    way:

        eff = do_thing()
        next_eff = resolve_effect(eff, first_result)
        next_eff = resolve_effect(next_eff, second_result)
        result = resolve_effect(next_eff, third_result)

    Equivalently, if you don't care about intermediate results:

        result = resolve_effect(
            resolve_effect(
                resolve_effect(
                    do_thing(),
                    first_result),
                second_result),
            third_result)

    NOTE: parallel effects have no special support. They can be resolved with
    a sequence, and if they're returned from another effect's callback they
    will be returned just like any other effect.
    """
    # It would be _cool_ if this could be implemented in terms of the Effect's
    # own machinery for running through callbacks, but the main difference
    # here is that we stop when we reach a new effect, instead of performing
    # recursively.
    for i, (callback, errback) in enumerate(effect.callbacks):
        cb = errback if is_error else callback
        if cb is None:
            continue
        try:
            is_error = False
            result = cb(result)
        except:
            is_error = True
            result = sys.exc_info()
        if type(result) is Effect:
            # Wrap all the remaining callbacks around the new effect we just
            # found, so that resolving it will run everything, and not just
            # the nested ones.
            return Effect.with_callbacks(
                result.intent,
                result.callbacks + effect.callbacks[i + 1:])
    if is_error:
        six.reraise(*result)
    return result


def fail_effect(effect, exception):
    """
    Resolve an effect with a failure, so its error handler will be run.
    """
    try:
        raise exception
    except:
        return resolve_effect(effect, sys.exc_info(), is_error=True)


def resolve_stub(effect):
    """
    Like resolve_effect, but automatically uses the result available in a
    StubIntent.
    """
    return resolve_effect(effect, effect.intent.result)


def sync_perform(effect, dispatcher=default_dispatcher):
    """
    Perform an effect, and return the value that its last callback or error
    handler returns. If the final callback raises an exception, the exception
    will be raised.

    This requires that the effect (and all effects returned from any of its
    callbacks) to be synchronous -- in other words, the effect performers
    must pass the result to the box before returning.

    If this is not the case, an AssertionError will be raised.
    """
    successes = []
    errors = []

    def SUCC(x):
        successes.append(x)

    def ERR(x):
        errors.append(x)

    effect = effect.on(success=SUCC, error=ERR)
    perform(effect, dispatcher=dispatcher)
    if successes:
        return successes[0]
    elif errors:
        six.reraise(*errors[0])
    else:
        raise AssertionError("Performing %r was not synchronous!" % (effect,))
