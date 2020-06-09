import React from "react";
import S2Link from "./S2Link";
import { Author } from "./types/api";

interface AuthorListProps {
  authors: Author[];
  showLinks?: boolean;
}

class AuthorList extends React.PureComponent<AuthorListProps, {}> {
  render() {
    return (
      <span className="author-list">
        {this.props.authors.map((author, i) => {
          let textConnector;
          if (i === 0) {
            textConnector = "";
          } else if (i === this.props.authors.length - 1) {
            textConnector = " and ";
          } else {
            textConnector = ", ";
          }
          var authorUrl = `https://www.semanticscholar.org/author/{author.id}`
          return (
            <span key={author.id}>
              {textConnector}
              {this.props.showLinks && (
                <S2Link url={authorUrl}>{author.name}</S2Link>
              )}
              {!this.props.showLinks && <>{author.name}</>}
            </span>
          );
        })}
      </span>
    );
  }
}

export default AuthorList;
