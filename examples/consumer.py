#!/usr/bin/env python
"""
Simple example for an OpenID consumer.

Once you understand this example you'll know the basics of OpenID
and using the Python OpenID library. You can then move on to more
robust examples, and integrating OpenID into your application.
"""
__copyright__ = 'Copyright 2005, Janrain, Inc.'

import cgi
import urlparse
import cgitb
import sys

def quoteattr(s):
    qs = cgi.escape(s, 1)
    return '"%s"' % (qs,)

from BaseHTTPServer import HTTPServer, BaseHTTPRequestHandler

# You may need to manually add the openid package into your
# python path if you don't have it installed with your system python.
# If so, uncomment the line below, and change the path where you have
# Python-OpenID.
# sys.path.append('/path/to/openid/')

from openid.stores import filestore
from openid.consumer import interface as openid
from openid.oidutil import appendArgs

class OpenIDHTTPServer(HTTPServer):
    """http server that contains a reference to an OpenID consumer and
    knows its base URL.
    """
    def __init__(self, consumer, *args, **kwargs):
        HTTPServer.__init__(self, *args, **kwargs)

        if self.server_port != 80:
            self.base_url = ('http://%s:%s/' %
                             (self.server_name, self.server_port))
        else:
            self.base_url = 'http://%s/' % (self.server_name,)

        self.openid_consumer = consumer

class OpenIDRequestHandler(BaseHTTPRequestHandler):
    """Request handler that knows how to verify an OpenID identity."""

    def do_GET(self):
        """Dispatching logic. There are three paths defined:

          / - Display an empty form asking for an identity URL to
              verify
          /verify - Handle form submission, initiating OpenID verification
          /process - Handle a redirect from an OpenID server

        Any other path gets a 404 response. This function also parses
        the query parameters.

        If an exception occurs in this function, a traceback is
        written to the requesting browser.
        """
        try:
            self.parsed_uri = urlparse.urlparse(self.path)
            self.query = {}
            for k, v in cgi.parse_qsl(self.parsed_uri[4]):
                self.query[k] = v

            path = self.parsed_uri[2]
            if path == '/':
                self.render()
            elif path == '/verify':
                self.doVerify()
            elif path == '/process':
                self.doProcess()
            else:
                self.notFound()

        except (KeyboardInterrupt, SystemExit):
            raise
        except:
            self.send_response(500)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(cgitb.html(sys.exc_info(), context=10))

    def doVerify(self):
        """Process the form submission, initating OpenID verification.
        """

        # First, make sure that the user entered something
        openid_url = self.query.get('openid_url')
        if not openid_url:
            self.render('Enter an identity URL to verify.',
                        css_class='error', form_contents=openid_url)
            return

        consumer = self.server.openid_consumer

        # Then, ask the library to begin the authorization.
        status, info = consumer.beginAuth(openid_url)

        # If the URL was unusable (either because of network
        # conditions, a server error, or that the response returned
        # was not an OpenID identity page), the library will return
        # None. Let the user know that that URL is unusable.
        if status in [openid.HTTP_FAILURE, openid.PARSE_ERROR]:
            if status == openid.HTTP_FAILURE:
                fmt = 'Failed to retrieve <q>%s</q>'
            else:
                fmt = 'Could not find OpenID information in <q>%s</q>'

            message = fmt % (cgi.escape(openid_url),)
            self.render(message, css_class='error', form_contents=openid_url)
        elif status == openid.SUCCESS:
            # The URL was a valid identity URL. Now we construct a URL
            # that will get us to process the server response. We will
            # need the token from the auth request when processing the
            # response, so we have to save it somewhere. The obvious
            # options are including it in the URL, storing it in a
            # cookie, and storing it in a session object if one is
            # available. For this example, we have no session and we
            # do not want to deal with cookies, so just add it as a
            # query parameter to the URL.
            return_to = self.buildURL('process', token=info.token)

            # Now ask the library for the URL to redirect the user to
            # his OpenID server. The auth request is what the library
            # returned before. We just constructed the return_to. The
            # return_to URL must be under the specified trust_root. We
            # just use the base_url for this server as a trust root.
            redirect_url = consumer.constructRedirect(
                info, return_to, trust_root=self.server.base_url)

            # Send the redirect response 
            self.redirect(redirect_url)
        else:
            assert False, 'Not reached'

    def doProcess(self):
        """Handle the redirect from the OpenID server.
        """
        consumer = self.server.openid_consumer

        # retrieve the token from the environment (in this case, the URL)
        token = self.query.get('token', '')

        # Ask the library to check the response that the server sent
        # us.  Status is a code indicating the response type. info is
        # either None or a string containing more information about
        # the return type.
        status, info = consumer.completeAuth(token, self.query)
        
        css_class = 'error'
        openid_url = None
        if status == openid.FAILURE and info:
            # In the case of failure, if info is non-None, it is the
            # URL that we were verifying. We include it in the error
            # message to help the user figure out what happened.
            openid_url = info
            fmt = "Verification of %s failed."
            message = fmt % (cgi.escape(openid_url),)
        elif status == openid.SUCCESS:
            # Success means that the transaction completed without
            # error. If info is None, it means that the user cancelled
            # the verification.
            css_class = 'alert'
            if info:
                # This is a successful verification attempt. If this
                # was a real application, we would do our login,
                # comment posting, etc. here.
                openid_url = info
                fmt = "You have successfully verified %s as your identity."
                message = fmt % (cgi.escape(openid_url),)
            else:
                # cancelled
                message = 'Verification cancelled'
        else:
            # Either we don't understand the code or there is no
            # openid_url included with the error. Give a generic
            # failure message. The library should supply debug
            # information in a log.
            message = 'Verification failed.'
            css_class = 'error'

        self.render(message, css_class, openid_url)

    def buildURL(self, action, **query):
        """Build a URL relative to the server base_url, with the given
        query parameters added."""
        base = urlparse.urljoin(self.server.base_url, action)
        return appendArgs(base, query)

    def redirect(self, redirect_url):
        """Send a redirect response to the given URL to the browser."""
        response = """\
Location: %s
Content-type: text/plain

Redirecting to %s""" % (redirect_url, redirect_url)
        self.send_response(302)
        self.wfile.write(response)

    def notFound(self):
        """Render a page with a 404 return code and a message."""
        fmt = 'The path <q>%s</q> was not understood by this server.'
        msg = fmt % (self.path,)
        openid_url = self.query.get('openid_url')
        self.render(msg, 'error', openid_url, status=404)

    def render(self, message=None, css_class='alert', form_contents=None,
               status=200, title="Python OpenID Consumer Example"):
        """Render a page."""
        self.send_response(status)
        self.pageHeader(title)
        if message:
            self.wfile.write("<div class='%s'>" % (css_class,))
            self.wfile.write(message)
            self.wfile.write("</div>")
        self.pageFooter(form_contents)

    def pageHeader(self, title):
        """Render the page header"""
        self.wfile.write('''\
Content-type: text/html

<html>
  <head><title>%s</title></head>
  <style type="text/css">
      * {
        font-family: verdana,sans-serif;
      }
      body {
        width: 50em;
        margin: 1em;
      }
      div {
        padding: .5em;
      }
      table {
        margin: none;
        padding: none;
      }
      .alert {
        border: 1px solid #e7dc2b;
        background: #fff888;
      }
      .error {
        border: 1px solid #ff0000;
        background: #ffaaaa;
      }
      #verify-form {
        border: 1px solid #777777;
        background: #dddddd;
        margin-top: 1em;
        padding-bottom: 0em;
      }
  </style>
  <body>
    <h1>%s</h1>
    <p>
      This example consumer uses the <a
      href="http://openid.schtuff.com/">Python OpenID</a> library. It
      just verifies that the URL that you enter is your identity URL.
    </p>
''' % (title, title))

    def pageFooter(self, form_contents):
        """Render the page footer"""
        if not form_contents:
            form_contents = ''

        self.wfile.write('''\
    <div id="verify-form">
      <form method="get" action=%s>
        Identity&nbsp;URL:
        <input type="text" name="openid_url" value=%s />
        <input type="submit" value="Verify" />
      </form>
    </div>
  </body>
</html>
''' % (quoteattr(self.buildURL('verify')), quoteattr(form_contents)))

def main(host, port, data_path):
    # Instantiate OpenID consumer store and OpenID consumer.  If you
    # were connecting to a database, you would create the database
    # connection and instantiate an appropriate store here.
    store = filestore.FileOpenIDStore(data_path)
    consumer = openid.OpenIDConsumer(store)

    addr = (host, port)
    server = OpenIDHTTPServer(consumer, addr, OpenIDRequestHandler)

    print 'Server running at:'
    print server.base_url
    server.serve_forever()

if __name__ == '__main__':
    host = 'localhost'
    data_path = 'cstore'
    port = 8000

    try:
        import optparse
    except ImportError:
        pass # Use defaults (for Python 2.2)
    else:
        parser = optparse.OptionParser('Usage:\n %prog [options]')
        parser.add_option(
            '-d', '--data-path', dest='data_path', default=data_path,
            help='Data directory for storing OpenID consumer state. '
            'Defaults to "%default" in the current directory.')
        parser.add_option(
            '-p', '--port', dest='port', type='int', default=port,
            help='Port on which to listen for HTTP requests. '
            'Defaults to port %default.')
        parser.add_option(
            '-s', '--host', dest='host', default=host,
            help='Host on which to listen for HTTP requests. '
            'Also used for generating URLs. Defaults to %default.')

        options, args = parser.parse_args()
        if args:
            parser.error('Expected no arguments. Got %r' % args)

        host = options.host
        port = options.port
        data_path = options.data_path

    main(host, port, data_path)